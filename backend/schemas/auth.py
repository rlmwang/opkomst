from datetime import datetime

from pydantic import BaseModel, Field

from .common import LowercaseEmail


class LoginLinkRequest(BaseModel):
    """Single entry point for both populations: a registered email
    receives a sign-in link, an unknown email receives a
    "finish creating your account" link. The endpoint returns the
    same response shape either way so the API can't be probed for
    account existence."""

    email: LowercaseEmail


class LoginRequest(BaseModel):
    """Redeems a magic-link token minted by /auth/login-link for an
    existing user. Single-use; the row is deleted on redemption."""

    token: str


class CompleteRegistrationRequest(BaseModel):
    """Redeems a registration token minted for an unknown email,
    supplying the only field we still need to create the user
    (their name). Returns an ``AuthResponse`` — completing
    registration is also the user's first sign-in."""

    token: str
    name: str = Field(min_length=1)


class ChapterRef(BaseModel):
    """Lightweight chapter reference embedded in ``UserOut``. Just
    enough for the frontend to render a chip without a second
    round-trip."""

    id: str
    name: str
    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_approved: bool
    # Live chapters the user belongs to, sorted by name. Soft-deleted
    # chapters are filtered out at the DTO layer so a user re-acquires
    # them automatically when an admin restores the chapter.
    chapters: list[ChapterRef]
    created_at: datetime
    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class LinkSent(BaseModel):
    """Boring 200 response so /login-link can't be probed for whether
    an email is registered."""

    status: str = "ok"
