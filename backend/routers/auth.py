import os
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import (
    create_purpose_token,
    create_token,
    decode_purpose_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..database import get_db
from ..models import User
from ..schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut, VerifyEmailRequest
from ..services import chapters as chapters_svc
from ..services import scd2
from ..services.email import build_url, send_email
from ..services.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

BOOTSTRAP_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").lower()
VERIFY_TOKEN_TTL_HOURS = 24


def _user_out(db, user: User) -> UserOut:
    """Materialise UserOut with the chapter_name resolved.
    ``id`` is always ``user.entity_id`` — the stable logical id."""
    return UserOut(
        id=user.entity_id,
        email=user.email,
        name=user.name,
        role=user.role,
        email_verified_at=user.email_verified_at,
        is_approved=user.is_approved,
        chapter_id=user.chapter_id,
        chapter_name=chapters_svc.name_for_entity(db, user.chapter_id),
        created_at=user.created_at,
    )


def _send_verification(user: User) -> None:
    token = create_purpose_token(user.entity_id, user.email, "verify-email", VERIFY_TOKEN_TTL_HOURS)
    verify_url = build_url("verify-email", token=token)
    send_email(
        to=user.email,
        template_name="verify.html",
        context={"name": user.name, "verify_url": verify_url},
        locale="nl",
    )


def _user_by_email(db: Session, email: str) -> User | None:
    """Resolve an email to its current user version."""
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


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit("5/hour")
def register(request: Request, data: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    if _user_by_email(db, data.email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    # If the email belongs to a soft-deleted account, restore the chain
    # instead of opening a new one. The new row carries the freshly
    # supplied password + name but lands unapproved + unverified — both
    # gates have to pass again before the account can act.
    closed = _last_closed_user_by_email(db, data.email)
    if closed is not None:
        user = scd2.scd2_restore(db, closed, changed_by=closed.entity_id)
        # Override the carried-forward values with the new registration's.
        user.password_hash = hash_password(data.password)
        user.name = data.name
        user.is_approved = False
        user.email_verified_at = None
        # Restore drops admin: a previously-deleted admin returning has
        # to be re-promoted by another admin.
        user.role = "organiser"
        db.commit()
        db.refresh(user)
        _send_verification(user)
        logger.info("user_restored_via_register", user_id=user.entity_id)
        return AuthResponse(token=create_token(user.entity_id), user=_user_out(db, user))

    # Bootstrap: the very first registration with the configured admin
    # email auto-promotes to admin AND auto-verifies the email — without
    # this carve-out there'd be no one to approve anyone.
    is_bootstrap = bool(
        BOOTSTRAP_ADMIN_EMAIL
        and data.email == BOOTSTRAP_ADMIN_EMAIL
        and scd2.current(db.query(User)).count() == 0
    )

    now = datetime.now(UTC)
    user = scd2.scd2_create(
        db,
        User,
        # Self-reference: every later mutation is signed by an admin or
        # by the user themselves; the very first row has no other
        # candidate, so we point at the user's own entity_id.
        changed_by="bootstrap",
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role="admin" if is_bootstrap else "organiser",
        is_approved=is_bootstrap,
        email_verified_at=now if is_bootstrap else None,
        chapter_id=None,
    )
    user.changed_by = user.entity_id
    db.commit()
    db.refresh(user)

    if not is_bootstrap:
        _send_verification(user)

    logger.info("user_registered", user_id=user.entity_id, bootstrap=is_bootstrap)
    return AuthResponse(token=create_token(user.entity_id), user=_user_out(db, user))


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = _user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return AuthResponse(token=create_token(user.entity_id), user=_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return _user_out(db, user)


@router.post("/verify-email", response_model=UserOut)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)) -> UserOut:
    payload = decode_purpose_token(data.token, "verify-email")
    user = scd2.current_by_entity(db, User, payload["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email != payload.get("email"):
        raise HTTPException(status_code=400, detail="Token email mismatch")
    if user.email_verified_at is None:
        new_user = scd2.scd2_update(
            db,
            user,
            changed_by=user.entity_id,
            email_verified_at=datetime.now(UTC),
        )
        db.commit()
        db.refresh(new_user)
        logger.info("email_verified", user_id=new_user.entity_id)
        return _user_out(db, new_user)
    return _user_out(db, user)


@router.post("/resend-verification", status_code=204)
def resend_verification(user: User = Depends(get_current_user)) -> None:
    if user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="Already verified")
    _send_verification(user)
    logger.info("verification_resent", user_id=user.entity_id)
