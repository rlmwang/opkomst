from pydantic import BaseModel, Field


class AfdelingOut(BaseModel):
    """One afdeling, current or archived. ``id`` is the entity_id (the
    stable logical identifier, what FKs from events / users point at).
    ``archived`` mirrors ``valid_until IS NOT NULL`` so the frontend
    doesn't need to inspect timestamps."""

    id: str  # entity_id, not the row id
    name: str
    archived: bool


class AfdelingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AfdelingUsageOut(BaseModel):
    """How many users / events are currently assigned to this
    afdeling. Used by the delete dialog so the admin sees what
    happens to dependents before confirming."""

    users: int
    events: int


class AfdelingArchiveRequest(BaseModel):
    """Optional reassignment targets when archiving an afdeling. Both
    default to None — neither is mandatory; rows that aren't
    reassigned simply stay linked to the about-to-be-archived
    entity_id (events become invisible until restore, users still
    have an afdeling_id pointing at the archived chapter)."""

    reassign_users_to: str | None = None
    reassign_events_to: str | None = None
