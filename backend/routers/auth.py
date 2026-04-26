import os

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user, hash_password, verify_password
from ..database import get_db
from ..models import User
from ..schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

BOOTSTRAP_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").lower()


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Bootstrap: the very first registration with the configured admin
    # email is auto-approved and promoted. This is the only auto-promotion
    # path; every other admin is granted by an existing admin.
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
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user_registered", user_id=user.id, bootstrap=is_bootstrap)
    return AuthResponse(token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return AuthResponse(token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
