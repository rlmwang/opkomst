import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user
from ..config import settings
from ..database import get_db
from ..models import LoginToken, User
from ..schemas.auth import (
    AuthResponse,
    LinkSent,
    LoginLinkRequest,
    LoginRequest,
    RegisterRequest,
    UserOut,
)
from ..services import chapters as chapters_svc
from ..services import scd2
from ..services.email.sender import send_email
from ..services.email.urls import build_url
from ..services.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

BOOTSTRAP_ADMIN_EMAIL = (
    settings.bootstrap_admin_email.lower() if settings.bootstrap_admin_email else ""
)
LOGIN_TOKEN_TTL_MINUTES = 30


def _user_out(db: Session, user: User) -> UserOut:
    """``id`` is always ``user.entity_id`` — the stable logical id."""
    return UserOut(
        id=user.entity_id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=user.is_approved,
        chapter_id=user.chapter_id,
        chapter_name=chapters_svc.name_for_entity(db, user.chapter_id),
        created_at=user.created_at,
    )


def _user_by_email(db: Session, email: str) -> User | None:
    return scd2.current(db.query(User)).filter(User.email == email).first()


def _last_closed_user_by_email(db: Session, email: str) -> User | None:
    """Most-recently-archived user row with this email, if any. Used
    by register so registering a previously-soft-deleted email
    restores the SCD2 chain instead of creating a new one."""
    return (
        db.query(User)
        .filter(User.email == email, User.valid_until.is_not(None))  # scd2-history-ok: restore lookup
        .order_by(User.valid_from.desc())
        .first()
    )


def _mint_login_token(db: Session, user: User) -> str:
    """Insert a fresh single-use token, return its raw value. The
    raw token is what the email link carries; redeem deletes the
    row so a clicked link can't be replayed."""
    raw = secrets.token_urlsafe(32)
    row = LoginToken(
        token=raw,
        user_id=user.entity_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=LOGIN_TOKEN_TTL_MINUTES),
    )
    db.add(row)
    db.commit()
    return raw


def _send_login_email(user: User, raw_token: str) -> None:
    url = build_url("auth/redeem", token=raw_token)
    send_email(
        to=user.email,
        template_name="login.html",
        context={"name": user.name, "login_url": url},
        locale="nl",
    )


@router.post("/login-link", response_model=LinkSent)
@limiter.limit("5/hour")
def login_link(
    request: Request, data: LoginLinkRequest, db: Session = Depends(get_db)
) -> LinkSent:
    """Send a magic-link email if the address is registered. Always
    returns 200 — never reveal whether the email exists."""
    user = _user_by_email(db, data.email)
    if user is not None:
        raw = _mint_login_token(db, user)
        _send_login_email(user, raw)
        logger.info("login_link_sent", user_id=user.entity_id)
    else:
        logger.info("login_link_unknown_email")
    return LinkSent()


@router.post("/register", response_model=LinkSent, status_code=201)
@limiter.limit("5/hour")
def register(
    request: Request, data: RegisterRequest, db: Session = Depends(get_db)
) -> LinkSent:
    """Create the account (or restore a previously-archived one) and
    send a magic link. The user becomes "real" only when they click
    the link — registration without redemption leaves an unapproved
    row that an admin still has to gate."""
    existing = _user_by_email(db, data.email)
    if existing is not None:
        # Don't 409 — that leaks email existence. Send a fresh login
        # link to the existing account instead, so the legitimate
        # owner of the address can always get in.
        raw = _mint_login_token(db, existing)
        _send_login_email(existing, raw)
        logger.info("register_existing_email", user_id=existing.entity_id)
        return LinkSent()

    closed = _last_closed_user_by_email(db, data.email)
    if closed is not None:
        user = scd2.scd2_restore(db, closed, changed_by=closed.entity_id)
        user.name = data.name
        user.is_approved = False
        # Restore drops admin: a previously-deleted admin returning has
        # to be re-promoted by another admin.
        user.role = "organiser"
        db.commit()
        db.refresh(user)
        logger.info("user_restored_via_register", user_id=user.entity_id)
    else:
        # Bootstrap: the very first registration with the configured
        # admin email auto-promotes to admin — without this carve-out
        # there'd be no one to approve anyone. The ``count()`` check
        # is a TOCTOU-prone hint, not the safety mechanism. The real
        # serialisation point is the partial-unique index
        # ``uq_users_email_current``: if two callers race past the
        # check, only one INSERT lands; the other raises
        # ``IntegrityError`` and we treat it like an existing-email
        # registration (mint a fresh link to the row that won the
        # race). ``scd2_create`` self-references ``changed_by`` to
        # the new entity_id when None is passed, so we don't write
        # the row twice.
        is_bootstrap = bool(
            BOOTSTRAP_ADMIN_EMAIL
            and data.email == BOOTSTRAP_ADMIN_EMAIL
            and scd2.current(db.query(User)).count() == 0
        )
        try:
            with db.begin_nested():
                user = scd2.scd2_create(
                    db,
                    User,
                    email=data.email,
                    name=data.name,
                    role="admin" if is_bootstrap else "organiser",
                    is_approved=is_bootstrap,
                    chapter_id=None,
                )
            db.commit()
            db.refresh(user)
            logger.info("user_registered", user_id=user.entity_id, bootstrap=is_bootstrap)
        except IntegrityError:
            db.rollback()
            existing = _user_by_email(db, data.email)
            if existing is None:
                # Constraint other than the email partial-unique fired —
                # don't swallow.
                raise
            raw = _mint_login_token(db, existing)
            _send_login_email(existing, raw)
            logger.info("register_race_lost", user_id=existing.entity_id)
            return LinkSent()

    raw = _mint_login_token(db, user)
    _send_login_email(user, raw)
    return LinkSent()


@router.post("/login", response_model=AuthResponse)
@limiter.limit("20/minute")
def login(
    request: Request, data: LoginRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    """Redeem a magic-link token. Single-use: the row is deleted on
    successful redemption so a forwarded link can't be replayed."""
    row = db.query(LoginToken).filter(LoginToken.token == data.token).first()
    if row is None:
        raise HTTPException(status_code=410, detail="Invalid or already-used link")
    if row.expires_at <= datetime.now(UTC):
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Login link has expired")

    user = scd2.current_by_entity(db, User, row.user_id)
    if user is None:
        # The user was archived between minting and redemption.
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Account no longer exists")

    db.delete(row)
    db.commit()
    logger.info("login_link_redeemed", user_id=user.entity_id)
    return AuthResponse(token=create_token(user.entity_id), user=_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return _user_out(db, user)


@router.post("/dev-issue-token", response_model=AuthResponse, include_in_schema=False)
def dev_issue_token(
    data: LoginLinkRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    """Local-mode-only test fixture. Mints a JWT for any
    registered email without going through the magic-link
    round-trip. Gated by ``settings.local_mode`` — returns 404
    in any other environment so prod can't call it.

    Used by Playwright e2e tests that can't read a magic link
    out of the email backend's structured log."""
    if not settings.local_mode:
        raise HTTPException(status_code=404, detail="Not found")
    user = _user_by_email(db, data.email)
    if user is None:
        raise HTTPException(status_code=404, detail="No such user")
    return AuthResponse(token=create_token(user.entity_id), user=_user_out(db, user))
