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
