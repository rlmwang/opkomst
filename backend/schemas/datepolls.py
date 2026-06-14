"""Pydantic DTOs for the Datepolls feature.

Organiser CRUD payloads carry the candidate-slot set (the server
diff-applies on update, matched on the natural key
``(on_date, start_time, end_time)``). ``DatepollListOut`` is the
lightweight list row (scalars + a computed date summary, no raw slot
list); ``DatepollOut`` is the single-poll shape. Public shapes are
``PublicDatepollOut`` (what ``/by-slug`` renders) and
``DatepollSubmitIn`` (the public submission). The tri-state
``Availability`` literal is the single source of truth for the three
values, re-imported by the service + submit handler.

A slot is a date with an optional time range: ``start_time`` and
``end_time`` are both NULL (whole-day slot) or both set (timed slot,
``end > start``). The schema enforces both-or-neither below.
"""

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import DisplayName, InstagramHandle
from .events import Locale

Availability = Literal["yes", "no", "maybe"]


class DatepollSlotIn(BaseModel):
    """One candidate slot on the create / update payload. The natural
    key is ``(on_date, start_time, end_time)`` — the editor sends a set
    of slots, never row ids, so there is no ``id`` field;
    ``apply_slots`` diffs on that triple and preserves the responses of
    slots that stay. Whole-day = both times NULL; timed = both set with
    ``end > start``."""

    on_date: date
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "DatepollSlotIn":
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("start_time and end_time must be set together (or both omitted for a whole-day slot)")
        if self.start_time is not None and self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class DatepollSlotOut(BaseModel):
    id: str
    on_date: date
    start_time: time | None = None
    end_time: time | None = None
    model_config = {"from_attributes": True}


class DatepollCreate(BaseModel):
    """Organiser create payload."""

    chapter_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    image_artist_instagram: InstagramHandle
    locale: Locale = "nl"
    slots: list[DatepollSlotIn] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _clean(self) -> "DatepollCreate":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Name is required")
        return self


class DatepollUpdate(DatepollCreate):
    """Same shape as create. Distinct class so OpenAPI distinguishes
    the two endpoints even though the body is identical."""


class DatepollListOut(BaseModel):
    """List-row DTO. Scalars plus a computed date summary
    (``date_count`` = distinct candidate days + earliest/latest), so a
    row is useful without shipping every slot — mirrors how
    ``EventOut`` carries ``attendee_count`` rather than the signup
    list."""

    id: str
    slug: str
    name: str
    locale: Locale
    chapter_id: str | None
    chapter_name: str | None
    archived: bool
    created_at: datetime
    date_count: int
    first_date: date | None = None
    last_date: date | None = None


class DatepollOut(DatepollListOut):
    """Single-poll DTO — the list fields plus the description and the
    full candidate-slot list (sorted by date then start time)."""

    description: str | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    slots: list[DatepollSlotOut] = Field(default_factory=list)


class PublicDatepollOut(BaseModel):
    """What the public fill-out page (``/d/{slug}``) reads."""

    id: str
    name: str
    description: str | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    locale: Locale
    slots: list[DatepollSlotOut]


class DatepollAnswerIn(BaseModel):
    """One answered slot on the public submit payload."""

    datepoll_slot_id: str
    availability: Availability


class DatepollSubmitIn(BaseModel):
    """Public submission. ``display_name`` is the shared pseudonym
    primitive (optional, <=100, real-or-not). ``note`` is one optional
    free-text note on the whole submission. ``answers`` carries one
    entry per slot the respondent set a state for."""

    display_name: DisplayName
    note: str | None = Field(default=None, max_length=280)
    answers: list[DatepollAnswerIn] = Field(max_length=200)


class DatepollSubmitAck(BaseModel):
    """Public submit response — the secret edit-link token, returned
    once so the page can render the magic edit link (never stored
    raw, never recoverable)."""

    edit_token: str


class DatepollEditOut(BaseModel):
    """Current values of a submission, for pre-filling the edit form
    (reached via the edit-link token). ``answers`` maps slot id →
    availability; ``note`` is the whole-submission note."""

    display_name: str | None
    note: str | None = None
    answers: dict[str, Availability]


class DatepollSlotSummary(BaseModel):
    """Per-slot aggregate on the organiser details page."""

    id: str
    on_date: date
    start_time: time | None = None
    end_time: time | None = None
    yes: int
    maybe: int
    no: int


class DatepollSummaryOut(BaseModel):
    """Organiser summary. ``submission_count`` is the number of
    fill-outs; ``best_slot_id`` is the most-yes slot (tie-break:
    fewest no), or ``None`` when there are no responses. ``notes`` are
    the non-empty submission notes, newest first."""

    submission_count: int
    slots: list[DatepollSlotSummary]
    best_slot_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class DatepollSubmissionOut(BaseModel):
    """One submission as a flat row for the CSV export. ``answers`` is
    keyed by ``datepoll_slot_id``. ``display_name`` is the self-chosen
    pseudonym (NULL = anonymous) — same privacy contract as the event
    sign-up name; ``note`` is the optional whole-submission note."""

    submission_id: str
    display_name: str | None
    note: str | None
    created_at: datetime
    answers: dict[str, str]
