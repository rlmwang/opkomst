from datetime import datetime

from pydantic import BaseModel, Field

from .common import LowercaseEmail


class LoginLinkRequest(BaseModel):
    """Single entry point for both populations: a registered email
    receives a sign-in link, an unknown email receives a
    "finish creating your account" link. The endpoint returns the
    same response shape either way so the API can't be probed for
    account existence.

    ``tenant`` is the organisation's slug — the first segment of the URL
    the sign-in page is served from. The door is per tenant: the same
    address can organise for two of them, as two accounts.

    ``None`` is the root's door, where an address *is* the account: no
    organisation, no approval, and no registration step — an address the
    app hasn't seen gets a personal account and a sign-in link in the
    same response as one it has."""

    email: LowercaseEmail
    tenant: str | None = None


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
    # ``organisation`` or ``personal`` — what the account *is*, which is
    # what decides whether the app shows admin pages, chapters and the
    # WhatsApp tool at all.
    tenant_kind: str
    # People one event / form / datepoll / roster of this account may
    # hold, or ``null`` when there is no ceiling. The organiser sees
    # their count against it on the detail pages; an organisation has
    # none, so the number simply isn't there to show.
    participant_cap: int | None
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
