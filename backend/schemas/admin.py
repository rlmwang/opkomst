from pydantic import BaseModel, Field


class PendingCountOut(BaseModel):
    """Tiny DTO for the navbar's pending-approval indicator. Admin-
    only — surfacing this to organisers would just be noise."""

    count: int


class ApproveUserRequest(BaseModel):
    """Approve a pending user, optionally also assigning them to
    chapters. The list may be empty — a freshly approved user
    with no chapters lands on the dashboard's onboarding banner
    where they self-pick. The admin doesn't have to know which
    chapters apply at approval time, which matters when the
    person who registered is the one with that context."""

    chapter_ids: list[str] = Field(default_factory=list)


class SetUserChaptersRequest(BaseModel):
    """Replace the user's full chapter membership set. ``min_length=1``
    keeps approved users in at least one chapter — emptying the set
    is the same as de-activating them, which is what the delete
    endpoint is for."""

    chapter_ids: list[str] = Field(min_length=1)


class RenameUserRequest(BaseModel):
    """Min-length=1 catches empty strings; the handler additionally
    strips whitespace and 422s on a name that's whitespace-only,
    since Pydantic's ``min_length`` doesn't strip."""

    name: str = Field(min_length=1)
