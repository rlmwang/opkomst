from pydantic import BaseModel, Field


class ChapterOut(BaseModel):
    """One chapter, current or archived. ``id`` is the entity_id (the
    stable logical identifier, what FKs from events / users point at).
    ``archived`` mirrors ``valid_until IS NOT NULL`` so the frontend
    doesn't need to inspect timestamps."""

    id: str  # entity_id, not the row id
    name: str
    archived: bool
    # Optional anchor city — display name + centroid coords. Used by
    # the event-creation address picker to bias suggestions toward
    # streets near this chapter's home town.
    city: str | None = None
    city_lat: float | None = None
    city_lon: float | None = None


class ChapterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ChapterPatch(BaseModel):
    """Partial update for a chapter. Either field may be omitted;
    the city tuple is all-or-nothing — passing ``city`` requires
    ``city_lat``/``city_lon`` (and vice versa) so we never end up
    with a city display name that has no coordinates."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    city_lat: float | None = Field(default=None, ge=-90, le=90)
    city_lon: float | None = Field(default=None, ge=-180, le=180)


class ChapterUsageOut(BaseModel):
    """How many users / events are currently assigned to this
    chapter. Used by the delete dialog so the admin sees what
    happens to dependents before confirming."""

    users: int
    events: int


class ChapterArchiveRequest(BaseModel):
    """Optional reassignment targets when archiving a chapter. Both
    default to None — neither is mandatory; rows that aren't
    reassigned simply stay linked to the about-to-be-archived
    entity_id (events become invisible until restore, users still
    have a chapter_id pointing at the archived chapter)."""

    reassign_users_to: str | None = None
    reassign_events_to: str | None = None
