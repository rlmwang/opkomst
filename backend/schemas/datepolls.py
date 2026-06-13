"""Pydantic DTOs for the Datepolls feature.

Organiser CRUD payloads carry the candidate-date set (the server
diff-applies on update, matched on ``on_date``). ``DatepollListOut``
is the lightweight list row (scalars + a computed date summary, no
raw date list); ``DatepollOut`` is the single-poll shape. Public
shapes are ``PublicDatepollOut`` (what ``/by-slug`` renders) and
``DatepollSubmitIn`` (the public submission). The tri-state
``Availability`` literal is the single source of truth for the three
values, re-imported by the service + submit handler.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .common import DisplayName, InstagramHandle
from .events import Locale

Availability = Literal["yes", "no", "maybe"]


class DatepollDateIn(BaseModel):
    """One candidate date on the create / update payload. The natural
    key is ``on_date`` — the editor sends a set of dates, never row
    ids, so there is no ``id`` field; ``apply_dates`` diffs on
    ``on_date`` and preserves the responses of dates that stay."""

    on_date: date


class DatepollDateOut(BaseModel):
    id: str
    on_date: date
    model_config = {"from_attributes": True}


class DatepollCreate(BaseModel):
    """Organiser create payload."""

    chapter_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    image_artist_instagram: InstagramHandle
    locale: Locale = "nl"
    dates: list[DatepollDateIn] = Field(default_factory=list, max_length=60)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class DatepollUpdate(DatepollCreate):
    """Same shape as create. Distinct class so OpenAPI distinguishes
    the two endpoints even though the body is identical."""


class DatepollListOut(BaseModel):
    """List-row DTO. Scalars plus a computed date summary
    (``date_count`` + earliest/latest), so a row is useful without
    shipping every date — mirrors how ``EventOut`` carries
    ``attendee_count`` rather than the signup list."""

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
    full candidate-date list (sorted by ``on_date``)."""

    description: str | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    dates: list[DatepollDateOut] = Field(default_factory=list)


class PublicDatepollOut(BaseModel):
    """What the public fill-out page (``/d/{slug}``) reads."""

    id: str
    name: str
    description: str | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    locale: Locale
    dates: list[DatepollDateOut]


class DatepollAnswerIn(BaseModel):
    """One answered date on the public submit payload."""

    datepoll_date_id: str
    availability: Availability
    comment: str | None = Field(default=None, max_length=280)


class DatepollSubmitIn(BaseModel):
    """Public submission. ``display_name`` is the shared pseudonym
    primitive (optional, <=100, real-or-not). ``answers`` carries one
    entry per date the respondent set a state for."""

    display_name: DisplayName
    answers: list[DatepollAnswerIn] = Field(max_length=60)


class DatepollSubmitAck(BaseModel):
    """Public submit response — the secret edit-link token, returned
    once so the page can render the magic edit link (never stored
    raw, never recoverable)."""

    edit_token: str


class DatepollEditValue(BaseModel):
    """One date's prior answer, for pre-filling the edit form."""

    availability: Availability
    comment: str | None = None


class DatepollEditOut(BaseModel):
    """Current values of a submission, for pre-filling the edit form
    (reached via the edit-link token). ``answers`` keyed by date id."""

    display_name: str | None
    answers: dict[str, DatepollEditValue]


class DatepollDateSummary(BaseModel):
    """Per-date aggregate on the organiser details page."""

    id: str
    on_date: date
    yes: int
    maybe: int
    no: int
    comments: list[str] = Field(default_factory=list)


class DatepollSummaryOut(BaseModel):
    """Organiser summary. ``submission_count`` is the number of
    fill-outs; ``best_date_id`` is the most-yes date (tie-break:
    fewest no), or ``None`` when there are no responses."""

    submission_count: int
    dates: list[DatepollDateSummary]
    best_date_id: str | None = None


class DatepollSubmissionOut(BaseModel):
    """One submission as a flat row for the CSV export. ``answers`` and
    ``comments`` are keyed by ``datepoll_date_id``. ``display_name`` is
    the self-chosen pseudonym (NULL = anonymous) — same privacy
    contract as the event sign-up name."""

    submission_id: str
    display_name: str | None
    created_at: datetime
    answers: dict[str, str]
    comments: dict[str, str]
