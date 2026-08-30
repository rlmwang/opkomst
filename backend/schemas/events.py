from collections.abc import Sequence
from datetime import date, datetime, time
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import BilingualTitleMixin, DisplayName, InstagramHandle, Locale, LowercaseEmail, RichText
from .feedback import FeedbackSummaryOut


class EventOptionIn(BaseModel):
    """One answer offered by a sign-up question, on the create / update
    payload. ``id`` carries the server's uuid for an option that already
    exists, which is what keeps existing sign-ups attached across a
    rename (``docs/design-question-edits.md``)."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=200)


class EventOptionOut(BaseModel):
    """One answer as anyone reading the event sees it. The id travels
    because a sign-up is submitted by id."""

    id: str
    label: str
    model_config = {"from_attributes": True}


class EventCreate(BilingualTitleMixin):
    """Create/edit payload for an event definition. Carries the shared
    content and the recurrence rule (the roster's k-week cycle) — never a
    single concrete date. A one-off is ``cycle_slots = []``; a recurring
    event picks weekday slots on a ``period_weeks`` cycle, running for
    ``span_weeks`` weeks (``None`` = open-ended). Concrete dates are
    ``Occurrence`` rows the tick materialises."""

    # Chapter that owns the event. Validated in the router against the
    # caller's membership set; the UI dropdown is already scoped to the
    # user's live chapters so this is a defence-in-depth check.
    #
    # ``None`` for a personal account, which has no chapters. Which of
    # the two is required is the actor's tenant's business, decided in
    # ``access.assert_user_can_assign_chapter`` — the schema can't know
    # who is posting.
    chapter_id: str | None = None
    topic_nl: RichText
    topic_en: RichText
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    # The recurrence rule (the chores roster's k-week cycle + a time of day).
    # ``starts_on`` anchors cycle week 0 and is the earliest occurrence date;
    # ``start_time`` / ``end_time`` are the shared wall-clock time of day.
    # ``period_weeks`` is the cycle length k. ``cycle_slots`` are the selected
    # weekday offsets (``week*7 + weekday``, Mon=0); ``[]`` is a one-off.
    # ``span_weeks`` runs the pattern that many weeks; ``None`` = open-ended.
    starts_on: date
    start_time: time
    end_time: time
    period_weeks: int = Field(default=1, ge=1, le=8)
    cycle_slots: list[int] = Field(default_factory=list, max_length=64)
    span_weeks: int | None = Field(default=None, ge=1, le=520)
    # How far ahead the tick materialises concrete occurrences + pages.
    horizon_days: int = Field(default=90, ge=1, le=730)

    # Each of the two sign-up questions has a switch. Off means the
    # question isn't asked, and then it needs no options; on, it needs
    # at least one, because a question with nothing to pick is a dead
    # control on the public page.
    #
    # Every switch starts off. An event asks for a name and a headcount
    # and nothing else until its organiser says otherwise: no extra
    # questions, no mail, and not on the agenda.
    source_options: list["EventOptionIn"] = Field(default_factory=list)
    source_enabled: bool = False
    image_artist_instagram: InstagramHandle
    help_options: list["EventOptionIn"] = Field(default_factory=list)
    help_enabled: bool = False
    feedback_enabled: bool = False
    reminder_enabled: bool = False
    listed: bool = False
    # Whether the public page insists on a (pseudo)name. Off by default
    # (``docs/design-public-pages-ux.md``): a name real or not is what
    # the contract offers, so an empty box is an answer.
    name_required: bool = False
    # Whether somebody may reopen their own link and change what they
    # sent in. On by default; withdrawing is never closed by it.
    answers_editable: bool = True
    locale: Locale = "nl"

    # On create an out-of-range cycle slot is a client bug and 422s; on
    # update (a lowered ``period_weeks``) now-orphan slots are clamped away,
    # mirroring ``RosterUpdate``.
    _clamp_out_of_range_slots: ClassVar[bool] = False

    @field_validator("start_time", "end_time")
    @classmethod
    def _time_must_be_naive(cls, v: time) -> time:
        if v.tzinfo is not None:
            raise ValueError(
                "Event times must be naive (Europe/Amsterdam wall clock); send 'HH:MM:SS' without a Z/offset."
            )
        return v

    @model_validator(mode="after")
    def _end_after_start(self) -> "EventCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    @model_validator(mode="after")
    def _normalise_cycle_slots(self) -> "EventCreate":
        hi = 7 * self.period_weeks
        slots = sorted(set(self.cycle_slots))
        if slots and slots[0] < 0:
            raise ValueError("cycle_slots entries must be >= 0")
        if self._clamp_out_of_range_slots:
            slots = [s for s in slots if s < hi]
        elif any(s >= hi for s in slots):
            raise ValueError(f"cycle_slots entries must be < {hi} (= 7 * period_weeks)")
        self.cycle_slots = slots
        return self

    @field_validator("source_options")
    @classmethod
    def _validate_source_options(cls, v: list["EventOptionIn"]) -> list["EventOptionIn"]:
        kept = [o for o in v if o.label.strip()]
        if len({o.label.strip() for o in kept}) != len(kept):
            raise ValueError("Source options must be unique")
        return kept

    @model_validator(mode="after")
    def _an_asked_question_needs_answers(self) -> "EventCreate":
        """A switched-on question with no options would render as an
        empty dropdown or an empty checklist on the public page. A
        switched-off one keeps whatever it has, so turning it back on
        restores the organiser's own list."""
        if self.source_enabled and not self.source_options:
            raise ValueError("At least one source option is required")
        if self.help_enabled and not self.help_options:
            raise ValueError("At least one help option is required")
        return self

    @field_validator("help_options")
    @classmethod
    def _validate_help_options(cls, v: list["EventOptionIn"]) -> list["EventOptionIn"]:
        kept = [o for o in v if o.label.strip()]
        if len({o.label.strip() for o in kept}) != len(kept):
            raise ValueError("Help options must be unique")
        return kept


class EventUpdate(EventCreate):
    """Edit payload. Same shape as create, but a lowered ``period_weeks``
    clamps now-out-of-range ``cycle_slots`` away instead of 422-ing."""

    _clamp_out_of_range_slots: ClassVar[bool] = True

    # An edit that deletes given answers is refused with a 409 saying
    # how many, and accepted when the same save comes back with this
    # set (``docs/design-question-edits.md``).
    confirm_destructive: bool = False


class EventListOut(BaseModel):
    """List-row DTO: what a dashboard card or an archive row draws, and
    nothing else. The sign-up form's own configuration (its questions,
    its toggles, its horizon, its image) belongs to the event's own page;
    shipping it per row put a whole edit form behind every card. Same
    split the other five products already make."""

    id: str
    name_nl: str | None
    name_en: str | None
    locale: Locale
    chapter_id: str | None
    chapter_name: str | None
    archived: bool
    # The card's meta line: where it is, and the map link behind it.
    location: str | None
    latitude: float | None
    longitude: float | None
    # An archived event has no next occurrence, so its row falls back to
    # the day the series began.
    starts_on: date
    start_time: time
    # The recurrence, in the three numbers the "weekly, 6 weeks" hint
    # reads. An empty ``cycle_slots`` is a one-off.
    period_weeks: int
    cycle_slots: list[int]
    span_weeks: int | None
    # Start of the soonest occurrence that hasn't ended yet — drives the
    # dashboard's "next: …" line and ordering. Null when every occurrence
    # is in the past (a finished course).
    next_starts_at: datetime | None
    # Public slug of that first-upcoming occurrence (falls back to the most
    # recent past one) — the link + QR target on the dashboard card and the
    # detail header. Null only for an event with no occurrences at all.
    next_slug: str | None
    # ``SUM(party_size)`` over the event's bookings (registrations) — how
    # many people have signed up for the course, each booking counted once
    # regardless of how many sessions it covers.
    attendee_count: int
    model_config = {"from_attributes": True}


class EventOut(EventListOut):
    """Organiser-side event DTO: everything a row carries, plus the
    definition of the sign-up form itself."""

    slug: str
    topic_nl: str | None
    topic_en: str | None
    end_time: time
    horizon_days: int
    source_options: list["EventOptionOut"]
    source_enabled: bool
    help_options: list["EventOptionOut"]
    help_enabled: bool
    feedback_enabled: bool
    reminder_enabled: bool
    listed: bool
    name_required: bool
    answers_editable: bool
    image_url: str | None
    image_artist_instagram: str | None


class OccurrenceOut(BaseModel):
    """One materialised occurrence in the organiser's read-only list."""

    id: str
    slug: str
    index: int
    starts_at: datetime
    ends_at: datetime
    # ``SUM(party_size)`` over registrations with a line item on this
    # occurrence — this session's headcount.
    attendee_count: int
    # Number of line items on this occurrence.
    signup_count: int


class ProjectedOccurrenceOut(BaseModel):
    """A beyond-horizon future date shown for context only: it has no row
    and no page yet, so it is not sign-up-able."""

    index: int
    starts_at: datetime
    ends_at: datetime


class OccurrenceListOut(BaseModel):
    """The occurrence list behind the organiser detail page's calendar day
    switcher: materialised occurrences with counts, plus the projected
    future dates. ``total_sessions`` is the "van N" (null = open-ended)."""

    total_sessions: int | None
    occurrences: list[OccurrenceOut]
    projected: list[ProjectedOccurrenceOut]


class EventPageOut(BaseModel):
    """Everything the organiser's event page draws, in one read.

    The page used to ask six times: the event, its sessions, the
    sign-ups and the stats of one session, and the feedback summary.
    Five of those are about the same event, and at eight organisers at
    once the waiting was the asking rather than any one answer.

    ``primary_occurrence_id`` is the session the page opens on, decided
    here rather than in the browser: the soonest that has not ended,
    else the last that ran. ``signups`` and ``stats`` are that session's;
    switching days asks for another one."""

    event: "EventOut"
    occurrences: "OccurrenceListOut"
    primary_occurrence_id: str | None
    signups: list["SignupSummaryOut"]
    stats: "EventStatsOut"
    feedback: FeedbackSummaryOut


class EventStatsOut(BaseModel):
    """Organiser-only aggregate over the event's sign-up line items
    (attendance is per occurrence, so these are per-line-item counts).
    Never includes individual signups."""

    total_signups: int  # number of line items
    total_attendees: int  # sum of party_size across line items
    by_source: dict[str, int]  # people per source answer
    by_help: dict[str, int]  # people per help option


class SignupSummaryOut(BaseModel):
    """A single line item as seen on the organiser's per-occurrence
    details page. Name + headcount come from the parent booking
    (registration); help-choices from the line item. Never email, source,
    or feedback-email status — the day's source breakdown is an aggregate
    (see the occurrence stats endpoint), never linked to a person. ``id`` is
    the line-item id (delete target); ``registration_id`` is the booking
    (edit-link recovery target)."""

    id: str
    registration_id: str
    display_name: str | None
    party_size: int
    link_recovered_at: datetime | None = None
    help_choices: list[str]


# --- Public sign-up surface ------------------------------------------


class PublicOccurrenceOut(BaseModel):
    """A materialised, sign-up-able occurrence on the public form's
    checklist. ``is_current`` marks the one whose page the visitor
    landed on (pre-selected)."""

    id: str
    slug: str
    index: int
    starts_at: datetime
    ends_at: datetime
    is_current: bool


class PublicEventOut(BaseModel):
    """The JSON the public per-occurrence sign-up page reads: the event
    content (read through the parent), the landing occurrence, the
    upcoming occurrences the visitor can also book, and the projected
    future dates shown as not-yet-open."""

    event_slug: str
    name_nl: str | None
    name_en: str | None
    topic_nl: str | None
    topic_en: str | None
    location: str | None
    latitude: float | None
    longitude: float | None
    # Empty when the organiser switched that question off. The page has
    # no business knowing about a question it isn't asking, so the
    # options simply aren't sent rather than being sent with a flag.
    source_options: Sequence["EventOptionOut"]
    help_options: Sequence["EventOptionOut"]
    image_url: str | None
    image_artist_instagram: str | None
    locale: Locale
    archived: bool
    # The mail this event will actually send. The page asks for an
    # address only when something is going to use it, and the privacy
    # disclosure names those uses one by one, so it has to know which
    # of them are switched on.
    reminder_enabled: bool
    feedback_enabled: bool
    # Whether the sign-up form insists on a (pseudo)name, and whether a
    # booking may still be changed through its own link.
    name_required: bool
    answers_editable: bool
    # Whether the event recurs (drives the calendar date picker vs a single
    # date on the public page). ``total_sessions`` is the "van N" for the
    # "sessie i van N" labels; null = open-ended.
    is_recurring: bool
    total_sessions: int | None
    # The occurrence the visitor landed on.
    current: PublicOccurrenceOut
    # Materialised, not-yet-ended occurrences (includes ``current``),
    # each selectable on the calendar. Ordered by date.
    upcoming: list[PublicOccurrenceOut]
    # Beyond-horizon future dates, shown for context, not selectable.
    projected: list[ProjectedOccurrenceOut]


class SignupCreate(BaseModel):
    """One public booking: a person and the occurrences they picked.
    Creates one registration with one line item per occurrence."""

    display_name: DisplayName
    party_size: int = Field(ge=1, le=50)
    # Option ids, not the labels a person read. An organiser fixing a
    # typo afterwards leaves both pointing at the same rows.
    source_choice: str | None = None
    help_choices: list[str] = Field(default_factory=list)
    # Optional — encrypted at rest, used once per occurrence for reminder
    # + feedback mail. The form surfaces the notice before this is shown.
    email: LowercaseEmail | None = None
    # The flag the visitor had active. Stored on the email-dispatch row so
    # reminder / feedback mail goes out in the recipient's own language;
    # null falls back to the event's primary locale in the router.
    locale: Locale | None = None
    # The occurrences to book. Ignored when ``all_upcoming`` is set (the
    # server resolves that to every future occurrence so a stale page
    # can't book a session already past). At least one is required
    # otherwise.
    occurrence_ids: list[str] = Field(default_factory=list)
    all_upcoming: bool = False

    @field_validator("help_choices")
    @classmethod
    def _validate_help_choices(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Help choices must be unique")
        return cleaned

    @model_validator(mode="after")
    def _needs_a_target(self) -> "SignupCreate":
        if not self.all_upcoming and not self.occurrence_ids:
            raise ValueError("Pick at least one occurrence, or set all_upcoming")
        # Dedupe posted ids so a double-checked box can't create two line
        # items for the same occurrence (the UNIQUE would 500 otherwise).
        self.occurrence_ids = list(dict.fromkeys(self.occurrence_ids))
        return self


class SignupAck(BaseModel):
    """Public response after a successful booking. Returns nothing
    identifying — just the secret edit-link token (shown once so the page
    can render the magic edit link; never stored raw, never recoverable)."""

    status: str = "ok"
    edit_token: str


# --- Public booking edit (by edit-link token) ------------------------


class BookingOccurrenceOut(BaseModel):
    """One occurrence a booking is on, as shown on the manage page.
    ``is_past`` marks a session that has already started: it is frozen
    history (attended), rendered locked and never editable."""

    occurrence_id: str
    slug: str
    index: int
    starts_at: datetime
    ends_at: datetime
    is_past: bool
    source_choice: str | None
    help_choices: list[str]


class BookingOccurrencesIn(BaseModel):
    """Replace a booking's **future** session set (the manage-page calendar).
    Past sessions are frozen and never referenced here. Same target shape as
    a sign-up: explicit ids, or ``all_upcoming`` for server resolution."""

    occurrence_ids: list[str] = Field(default_factory=list)
    all_upcoming: bool = False

    @model_validator(mode="after")
    def _dedupe(self) -> "BookingOccurrencesIn":
        self.occurrence_ids = list(dict.fromkeys(self.occurrence_ids))
        return self


class BookingOut(BaseModel):
    """The whole booking behind an edit-link token: the person's details,
    the occurrences they're on, and the event content needed to render."""

    display_name: str | None
    party_size: int
    link_recovered_at: datetime | None = None
    event_name: str
    event_slug: str
    locale: Locale
    occurrences: list[BookingOccurrenceOut]


class BookingEditIn(BaseModel):
    """Edit the booking-level fields (name + headcount). Per-occurrence
    membership is changed by withdrawing individual occurrences, not
    here. Email + dispatch rows are unreachable from a booking
    (principle #2)."""

    display_name: DisplayName
    party_size: int = Field(ge=1, le=50)
