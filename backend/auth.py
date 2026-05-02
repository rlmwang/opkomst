from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

_JWT_SECRET = settings.jwt_secret.get_secret_value()
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 24 * 7

ROLE_RANK: dict[str, int] = {"organiser": 1, "admin": 2}


def create_token(user_id: str) -> str:
    """Sign a JWT against the user's stable ``id``. Soft-delete
    invalidates the JWT (``get_current_user`` rejects via the
    ``deleted_at IS NULL`` filter); rotation of ``JWT_SECRET``
    is the only blanket revocation."""
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=JWT_TTL_HOURS)}
    return jwt.encode(payload, _JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
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
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def require_approved(user: User = Depends(get_current_user)) -> User:
    """An admin must have approved the account before an organiser can
    do anything beyond fetching /me. Email ownership is implicit —
    the user only got a JWT by clicking a magic link delivered to
    their address."""
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account is awaiting admin approval")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account is awaiting admin approval")
    return user
