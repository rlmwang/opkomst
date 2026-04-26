import os
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, Header
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 24 * 7

ROLE_RANK: dict[str, int] = {"organiser": 1, "admin": 2}


def hash_password(password: str) -> str:
    # bcrypt caps input at 72 bytes; truncate to be explicit instead of letting
    # the library raise. Pre-hashing with sha256 would be the alternative but
    # adds operational complexity for negligible benefit at our scale.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))


def create_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=JWT_TTL_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# --- Purpose tokens (email verification, password reset) ---


def create_purpose_token(user_id: str, email: str, purpose: str, expires_hours: int) -> str:
    """A signed, short-lived token tied to one user + purpose. Used in
    email links so the link itself proves the user controls the address."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_purpose_token(token: str, expected_purpose: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired token") from exc
    if payload.get("purpose") != expected_purpose:
        raise HTTPException(status_code=400, detail="Invalid token")
    return payload


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return sub


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    user_id = _decode_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def require_approved(user: User = Depends(get_current_user)) -> User:
    """Two gates: the user must have confirmed their email AND an admin
    must have approved their account. Both have to hold before an
    organiser can do anything beyond fetching /me."""
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email not verified")
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account is awaiting admin approval")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email not verified")
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account is awaiting admin approval")
    return user
