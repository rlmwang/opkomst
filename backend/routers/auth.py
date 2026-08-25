"""Magic-link auth.

One door per organisation: ``POST /auth/login-link`` accepts an email
plus the tenant slug the sign-in page is served from, and emails a
single-use link into that organisation. The same address in two
organisations is two accounts.

* Email already belongs to a live user of that tenant → ``LoginToken``
  minted, the link goes to ``/{tenant}/auth/redeem`` and
  ``POST /auth/login`` exchanges it for a JWT carrying the tenant.
* Email is unknown there (or only matches a soft-deleted row) →
  ``RegistrationToken`` minted (carrying the tenant), the link goes to
  ``/{tenant}/register/complete`` and ``POST /auth/complete-registration``
  takes the user's name, creates (or restores) the row, and
  returns a JWT — completing the sign-up logs the user in in the
  same step.

The public ``LinkSent`` response is identical for both branches so
the endpoint can't be probed for account existence.
"""

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user
from ..config import settings
from ..database import get_db
from ..models import LoginToken, RegistrationToken, User
from ..schemas.auth import (
    AuthResponse,
    ChapterRef,
    CompleteRegistrationRequest,
    LinkSent,
    LoginLinkRequest,
    LoginRequest,
    UserOut,
)
from ..services import limits, tenancy
from ..services import tenants as tenants_svc
from ..services.mail import build_url, send_email
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

BOOTSTRAP_ADMIN_EMAIL = settings.bootstrap_admin_email.lower() if settings.bootstrap_admin_email else ""
LOGIN_TOKEN_TTL_MINUTES = 30
REGISTRATION_TOKEN_TTL_MINUTES = 30


def _user_out(db: Session, user: User) -> UserOut:
    # Soft-deleted chapters drop out of the DTO so the frontend
    # never has to filter them client-side. The relationship is
    # ``selectin``-loaded so this is a single extra query, not N+1.
    live_chapters = sorted(
        (c for c in user.chapters if c.deleted_at is None),
        key=lambda c: c.name.lower(),
    )
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=user.is_approved,
        tenant_kind=user.tenant.kind,
        participant_cap=limits.participant_cap(user.tenant),
        chapters=[ChapterRef(id=c.id, name=c.name) for c in live_chapters],
        created_at=user.created_at,
    )


def _live_user_by_email(db: Session, email: str, tenant_id: str) -> User | None:
    """Live (not soft-deleted) user with this email in this tenant, or
    None. Scoped: the same address is a separate account per
    organisation."""
    return db.query(User).filter(User.email == email, User.tenant_id == tenant_id, User.deleted_at.is_(None)).first()


def _deleted_user_by_email(db: Session, email: str, tenant_id: str) -> User | None:
    """Soft-deleted user row with this email in this tenant, if any.
    Used by complete-registration so re-registering a previously-deleted
    email restores the row in place rather than creating a new
    one."""
    return (
        db.query(User)
        .filter(User.email == email, User.tenant_id == tenant_id, User.deleted_at.is_not(None))
        .order_by(User.deleted_at.desc())
        .first()
    )


def _mint_login_token(db: Session, user: User) -> str:
    """Insert a fresh single-use login token, return its raw value.
    The raw token is what the email link carries; redeem deletes the
    row so a clicked link can't be replayed."""
    raw = secrets.token_urlsafe(32)
    row = LoginToken(
        token=raw,
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(minutes=LOGIN_TOKEN_TTL_MINUTES),
    )
    db.add(row)
    db.commit()
    return raw


def _mint_registration_token(db: Session, email: str, tenant_id: str) -> str:
    """Insert a fresh single-use registration token for an email
    unknown *to this tenant*, return its raw value. Existing tokens for
    the same email in the same tenant are deleted first so only the
    most recent link in the inbox works — keeps the user-visible
    behaviour intuitive when they hit "send link" twice."""
    db.query(RegistrationToken).filter(
        RegistrationToken.email == email, RegistrationToken.tenant_id == tenant_id
    ).delete()
    raw = secrets.token_urlsafe(32)
    row = RegistrationToken(
        token=raw,
        email=email,
        expires_at=datetime.now(UTC) + timedelta(minutes=REGISTRATION_TOKEN_TTL_MINUTES),
    )
    db.add(row)
    db.commit()
    return raw


def _send_login_email(user: User, tenant_slug: str | None, raw_token: str, account: str) -> None:
    """``tenant_slug`` is ``None`` for a personal account, whose app is
    the root — so is its redeem link.

    ``account`` is what the mail calls the account this link opens: the
    organisation's name, or the address itself for a personal account.
    A reader who holds two of them can tell which one they're opening
    before they click, without the mail naming the other."""
    path = f"{tenant_slug}/auth/redeem" if tenant_slug else "auth/redeem"
    url = build_url(path, token=raw_token)
    send_email(
        to=user.email,
        template_name="login.html",
        context={"name": user.name, "login_url": url, "account": account},
        locale="nl",
    )


def _send_register_complete_email(email: str, tenant_slug: str, raw_token: str, account: str) -> None:
    """Only an organisation has a registration step — the root's door
    creates the account outright. ``account`` is the organisation's
    name, so the reader knows what they are joining."""
    url = build_url(f"{tenant_slug}/register/complete", token=raw_token)
    send_email(
        to=email,
        template_name="register_complete.html",
        context={"complete_url": url, "account": account},
        locale="nl",
    )


@router.post("/login-link", response_model=LinkSent)
@limiter.limit(Limits.AUTH)
def login_link(request: Request, data: LoginLinkRequest, db: Session = Depends(get_db)) -> LinkSent:
    """Send a magic link.

    Two doors. With a ``tenant`` it is an organisation's: the address
    either belongs to a live user of it (sign-in link) or doesn't
    (registration link, which asks for a name and waits for an admin).

    Without one it is the root's, where an address *is* the account.
    There is nobody to tell apart and nobody to approve you, so an
    address the app hasn't seen gets a personal tenant, its one user,
    and a sign-in link — the same response, and the same mail, as one it
    has seen.

    Both doors return the same ``LinkSent`` either way, so neither can
    be probed for which addresses or which organisations exist."""
    if data.tenant is None:
        return _personal_login_link(db, data.email)

    tenant = tenants_svc.find_live_organisation_by_slug(db, data.tenant)
    if tenant is None:
        logger.info("login_link_for_unknown_tenant")
        return LinkSent()
    # Binds the tenant for the token row this request is about to
    # write; nothing else in the flow has a signed-in user to bind it.
    tenancy.bind(tenant.id, tenant.brand_slug)

    user = _live_user_by_email(db, data.email, tenant.id)
    if user is not None:
        raw = _mint_login_token(db, user)
        _send_login_email(user, tenant.slug, raw, tenant.name)
        logger.info("login_link_sent", user_id=user.id)
    else:
        raw = _mint_registration_token(db, data.email, tenant.id)
        _send_register_complete_email(data.email, tenant.slug, raw, tenant.name)
        logger.info("register_link_sent_for_unknown_email")
    return LinkSent()


def _personal_login_link(db: Session, email: str) -> LinkSent:
    """The root's door: resolve the address to its personal account,
    creating it if this is the first time, and always mail a sign-in
    link. No registration token, no name prompt, no approval — the
    account is the address."""
    user = tenants_svc.resolve_personal(db, email)
    db.commit()
    tenancy.bind(user.tenant_id, user.tenant.brand_slug)
    raw = _mint_login_token(db, user)
    _send_login_email(user, None, raw, user.email)
    logger.info("personal_login_link_sent")
    return LinkSent()


def _restore_deleted(db: Session, deleted: User, name: str) -> User:
    """Re-open a soft-deleted user. Strips admin role on principle:
    a previously-deleted admin returning must be re-promoted by
    another admin."""
    deleted.deleted_at = None
    deleted.name = name
    deleted.is_approved = False
    deleted.role = "organiser"
    db.commit()
    db.refresh(deleted)
    return deleted


def _create_fresh_with_race_recovery(db: Session, email: str, name: str, tenant_id: str) -> User | None:
    """Insert a new user row. Returns the new row, or ``None`` if a
    concurrent completion lost the race on the partial-unique
    ``uq_users_email_live`` index — caller treats that as a
    "link-already-redeemed" 410.

    Bootstrap carve-out: the very first registration matching
    ``BOOTSTRAP_ADMIN_EMAIL`` lands as ``role=admin,
    is_approved=true``. The ``count() == 0`` check is a hint, not
    the safety mechanism — the partial-unique index is the
    serialisation point. Two concurrent bootstrap completions will
    both see ``count == 0``, both attempt INSERT, the second hits
    ``IntegrityError`` and the loser returns ``None``."""
    is_bootstrap = bool(
        BOOTSTRAP_ADMIN_EMAIL
        and email == BOOTSTRAP_ADMIN_EMAIL
        and db.query(User).filter(User.tenant_id == tenant_id, User.deleted_at.is_(None)).count() == 0
    )
    try:
        with db.begin_nested():
            user = User(
                email=email,
                name=name,
                role="admin" if is_bootstrap else "organiser",
                is_approved=is_bootstrap,
            )
            db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("user_registered", user_id=user.id, bootstrap=is_bootstrap)
        return user
    except IntegrityError:
        db.rollback()
        return None


@router.post("/complete-registration", response_model=AuthResponse)
@limiter.limit(Limits.LOGIN_REDEEM)
def complete_registration(
    request: Request,
    data: CompleteRegistrationRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Redeem a registration token + supply the user's name. Creates
    (or restores) the user and returns a JWT — completing
    registration is the user's first sign-in.

    Single-use: the token row is deleted on every terminal outcome
    (success, expired, race) so a clicked link can't be replayed
    and orphan rows don't accumulate."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")

    row = db.query(RegistrationToken).filter(RegistrationToken.token == data.token).first()
    if row is None:
        raise HTTPException(status_code=410, detail="Invalid or already-used link")
    if row.expires_at <= datetime.now(UTC):
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Registration link has expired")

    email = row.email
    # The tenant travelled on the token row, minted by the sign-in page
    # of one organisation — the completing user never picks it.
    tenant_id = row.tenant_id
    tenancy.bind(tenant_id, row.tenant.brand_slug)

    # Three convergent branches, same observable outcome (a usable
    # JWT for a row keyed to ``email``):
    #   1. Live user exists already (concurrent flow finished
    #      first, or the email was registered between mint and
    #      redeem) → 410. The token is single-use; we don't want
    #      a stranger who guessed a token to be able to "complete"
    #      registration into someone else's account.
    #   2. Soft-deleted user exists → restore in place, preserving
    #      ``user.id`` so any historical references keep working.
    #   3. Otherwise insert fresh, with bootstrap carve-out and
    #      race-recovery on the partial-unique email index.
    existing = _live_user_by_email(db, email, tenant_id)
    if existing is not None:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="An account with this email already exists")

    deleted = _deleted_user_by_email(db, email, tenant_id)
    if deleted is not None:
        user = _restore_deleted(db, deleted, name)
        log_event = "user_restored_via_complete_registration"
    else:
        user = _create_fresh_with_race_recovery(db, email, name, tenant_id)
        if user is None:
            # Lost the partial-unique race against a concurrent
            # completion. The race winner now owns the row.
            db.delete(row)
            db.commit()
            raise HTTPException(
                status_code=410,
                detail="An account with this email already exists",
            )
        log_event = "user_registered_via_complete_registration"

    db.delete(row)
    db.commit()
    logger.info(log_event, user_id=user.id)
    return AuthResponse(token=create_token(user), user=_user_out(db, user))


@router.post("/login", response_model=AuthResponse)
@limiter.limit(Limits.LOGIN_REDEEM)
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Redeem a login token. Single-use: the row is deleted on
    successful redemption so a forwarded link can't be replayed."""
    row = db.query(LoginToken).filter(LoginToken.token == data.token).first()
    if row is None:
        raise HTTPException(status_code=410, detail="Invalid or already-used link")
    if row.expires_at <= datetime.now(UTC):
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Login link has expired")

    user = db.query(User).filter(User.id == row.user_id, User.deleted_at.is_(None)).first()
    if user is None:
        # The user was deleted between minting and redemption.
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Account no longer exists")

    db.delete(row)
    db.commit()
    logger.info("login_link_redeemed", user_id=user.id)
    return AuthResponse(token=create_token(user), user=_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return _user_out(db, user)


@router.post("/logout", status_code=204)
@limiter.limit(Limits.ORG_RARE)
async def logout(request: Request, _: User = Depends(get_current_user)) -> None:
    """Sign-out hook. JWT is stateless so there's nothing to revoke
    server-side; the route exists so app-logout can also tear down
    the WhatsApp blast tool's linked-device session (otherwise a
    user closes the app and the linked phone stays paired with
    Evolution until the watchdog catches up).

    Best-effort: a failure here must not block sign-out — the
    frontend clears its JWT regardless. Errors are swallowed and
    logged, never raised."""
    from ..services import whatsapp as wa  # noqa: PLC0415 — keep auth's import surface small

    if wa.is_configured():
        try:
            await wa.delete_instance()
        except Exception:
            logger.warning("auth_logout_whatsapp_teardown", outcome="error")
