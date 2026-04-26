import os
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
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
from ..services import afdelingen as afdelingen_svc
from ..services.email import build_url, send_email

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

BOOTSTRAP_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").lower()
VERIFY_TOKEN_TTL_HOURS = 24


def _user_out(db, user: User) -> UserOut:
    """Materialise UserOut with the afdeling_name resolved. Plain
    model_validate misses afdeling_name because it lives in a separate
    table; a small helper keeps every endpoint that returns UserOut
    consistent."""
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        email_verified_at=user.email_verified_at,
        is_approved=user.is_approved,
        afdeling_id=user.afdeling_id,
        afdeling_name=afdelingen_svc.name_for_entity(db, user.afdeling_id),
        created_at=user.created_at,
    )


def _send_verification(user: User) -> None:
    token = create_purpose_token(user.id, user.email, "verify-email", VERIFY_TOKEN_TTL_HOURS)
    verify_url = build_url("verify-email", token=token)
    send_email(
        to=user.email,
        template_name="verify.html",
        context={"name": user.name, "verify_url": verify_url},
        locale="nl",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Bootstrap: the very first registration with the configured admin
    # email auto-promotes to admin AND auto-verifies the email — without
    # this carve-out there'd be no one to approve anyone. Every other
    # registration goes through both gates: email verification + admin
    # approval.
    is_bootstrap = bool(
        BOOTSTRAP_ADMIN_EMAIL
        and data.email == BOOTSTRAP_ADMIN_EMAIL
        and db.query(User).count() == 0
    )

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role="admin" if is_bootstrap else "organiser",
        is_approved=is_bootstrap,
        email_verified_at=datetime.now(UTC) if is_bootstrap else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if not is_bootstrap:
        _send_verification(user)

    logger.info("user_registered", user_id=user.id, bootstrap=is_bootstrap)
    return AuthResponse(token=create_token(user.id), user=_user_out(db, user))


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Login itself succeeds even without verification + approval — the
    # client uses /me to render the appropriate awaiting-... empty
    # state. Real action paths are gated by require_approved.
    return AuthResponse(token=create_token(user.id), user=_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return _user_out(db, user)


@router.post("/verify-email", response_model=UserOut)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)) -> UserOut:
    payload = decode_purpose_token(data.token, "verify-email")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email != payload.get("email"):
        # Email changed since the token was minted — reject rather than
        # silently verifying the new address.
        raise HTTPException(status_code=400, detail="Token email mismatch")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        db.commit()
        logger.info("email_verified", user_id=user.id)
    db.refresh(user)
    return _user_out(db, user)


@router.post("/resend-verification", status_code=204)
def resend_verification(user: User = Depends(get_current_user)) -> None:
    if user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="Already verified")
    _send_verification(user)
    logger.info("verification_resent", user_id=user.id)
