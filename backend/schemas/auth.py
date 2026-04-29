from datetime import datetime

from pydantic import BaseModel, Field

from .common import LowercaseEmail


class LoginLinkRequest(BaseModel):
    email: LowercaseEmail


class LoginRequest(BaseModel):
    """Redeems a magic-link token. The token was minted by
    ``/auth/login-link`` (existing user) or ``/auth/register`` (new
    user); both flows funnel into this single redemption endpoint."""

    token: str


class RegisterRequest(BaseModel):
    email: LowercaseEmail
    name: str = Field(min_length=1)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_approved: bool
    chapter_id: str | None
    chapter_name: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class LinkSent(BaseModel):
    """Boring 200 response so /login-link and /register don't leak
    whether an email exists."""

    status: str = "ok"
