"""Pydantic DTOs for the Chores feature (Dutch: takenroosters).

Organiser CRUD payloads carry the chore set (the server diff-applies on
update, matched on chore ``id`` like form questions). ``RosterListOut``
is the lightweight list row (scalars + counts, no chore list);
``RosterOut`` is the single-roster shape. ``PublicRosterOut`` is the
public ``/by-slug`` projection (consumed in task 05).

Recurrence is a k-week cycle (``period_weeks``), set once per roster. A
chore's ``cycle_slots`` are flat offsets ``week*7 + weekday`` into that
cycle, range ``0 .. 7*period_weeks - 1``, Mon=0. When k>1 the cycle
anchors on the first Monday on/after ``starts_on`` (derived, not stored).

Out-of-range ``cycle_slots`` are rejected on **create** (422) but
**clamped** (dropped) on **update**, so shrinking k drops the now-orphan
slots rather than failing the save (the UI warns — task 04). The two
classes differ only by the ``_clamp_out_of_range_slots`` class flag.
"""

from datetime import date, datetime
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from .common import DisplayName, InstagramHandle, Locale, LowercaseEmail


class ChoreIn(BaseModel):
    """One chore on the create / update payload. ``id`` is null for a new
    chore and set for an existing one (matched on update, like
    ``FormQuestionIn``). ``cycle_slots`` are normalised (deduped, sorted,
    range-checked) by the parent roster validator against ``period_weeks``."""

    id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    cycle_slots: list[int] = Field(default_factory=list, max_length=64)
    people_per_shift: int = Field(default=1, ge=1, le=20)
    emoji: str | None = Field(default=None, max_length=8)


class ChoreOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    ordinal: int
    cycle_slots: list[int]
    people_per_shift: int
    emoji: str | None = None
    model_config = {"from_attributes": True}


class RosterCreate(BaseModel):
    """Organiser create payload. Out-of-range ``cycle_slots`` raise 422."""

    _clamp_out_of_range_slots: ClassVar[bool] = False

    chapter_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    image_artist_instagram: InstagramHandle
    locale: Locale = "nl"
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    # k-week recurrence cycle. When k>1 the cycle anchors on the first
    # Monday on/after ``starts_on`` (derived). Cap k at 8 — the cycle grid
    # would be unwieldy beyond.
    period_weeks: int = Field(default=1, ge=1, le=8)
    starts_on: date
    ends_on: date | None = None
    reminder_enabled: bool = True
    reminder_days_before: int = Field(default=1, ge=0, le=14)
    chores: list[ChoreIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _validate(self) -> "RosterCreate":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Name is required")
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        hi = 7 * self.period_weeks
        for chore in self.chores:
            chore.name = chore.name.strip()
            slots = sorted(set(chore.cycle_slots))
            if slots and slots[0] < 0:
                raise ValueError("cycle_slots entries must be non-negative")
            if self._clamp_out_of_range_slots:
                slots = [s for s in slots if s < hi]
            elif any(s >= hi for s in slots):
                raise ValueError(f"cycle_slots entries must be < {hi} (= 7 * period_weeks)")
            chore.cycle_slots = slots
        return self


class RosterUpdate(RosterCreate):
    """Same body as create, but shrinking ``period_weeks`` drops (clamps)
    now-out-of-range ``cycle_slots`` instead of rejecting the save."""

    _clamp_out_of_range_slots: ClassVar[bool] = True


class RosterListOut(BaseModel):
    """List-row DTO. Scalars + counts, no chore list — mirrors how the
    other entities ship counts rather than the child collection."""

    id: str
    slug: str
    name: str
    locale: Locale
    chapter_id: str | None
    chapter_name: str | None
    archived: bool
    created_at: datetime
    period_weeks: int
    chore_count: int
    volunteer_count: int


class RosterOut(RosterListOut):
    """Single-roster DTO — list fields plus the recurrence config, the
    optional location/image, and the full chore list (by ordinal)."""

    description: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    starts_on: date
    ends_on: date | None = None
    reminder_enabled: bool
    reminder_days_before: int
    chores: list[ChoreOut] = Field(default_factory=list)


class PublicRosterOut(BaseModel):
    """What the public enrol page (``/c/{slug}``) reads."""

    id: str
    name: str
    description: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    locale: Locale
    period_weeks: int
    starts_on: date
    ends_on: date | None = None
    chores: list[ChoreOut] = Field(default_factory=list)


# --- Public enrolment + personal page --------------------------------


class PersonalShiftOut(BaseModel):
    """One shift on a volunteer's personal page. Populated from task 06;
    the shape is fixed here so the response model + frontend are stable."""

    id: str
    chore_id: str
    chore_name: str
    on_date: date
    status: str


class EnrollIn(BaseModel):
    """Public enrolment. ``email`` is optional; if given and
    ``email_reminders`` is on, it's retained (encrypted) for reminders —
    otherwise it's used once for the welcome link and not stored (§6)."""

    display_name: DisplayName
    email: LowercaseEmail | None = None
    email_reminders: bool = False
    chore_ids: list[str] = Field(default_factory=list, max_length=100)


class EnrollAck(BaseModel):
    """Enrol response — the secret personal-page token, shown once."""

    edit_token: str


class EnrollEditIn(BaseModel):
    """Edit an enrolment via the personal-page token. ``email`` is an
    optional add/replace; reminder/email transitions follow §6."""

    display_name: DisplayName
    chore_ids: list[str] = Field(default_factory=list, max_length=100)
    email_reminders: bool = False
    email: LowercaseEmail | None = None


class PersonalPageOut(BaseModel):
    """The volunteer's personal page. Never carries the email or its
    ciphertext — only whether one is on file (``has_email``)."""

    display_name: str | None
    enrolled_chore_ids: list[str]
    email_reminders: bool
    has_email: bool
    my_shifts: list[PersonalShiftOut] = Field(default_factory=list)
    open_shifts: list[PersonalShiftOut] = Field(default_factory=list)


class VolunteerSummaryOut(BaseModel):
    """Organiser-facing volunteer row: pseudonym + enrolled chores +
    assignment load + lifetime accountability counts. **Never** the
    email, ciphertext, or edit token.

    ``load`` is current upcoming responsibility (scheduled + done);
    ``assigned`` is how many shifts they've ever taken on (auto-assigned
    + self-claimed); ``completed`` / ``deferred`` / ``missed`` are the
    resolved outcomes so far."""

    id: str
    display_name: str | None
    enrolled_chore_ids: list[str]
    load: int
    assigned: int
    completed: int
    deferred: int
    missed: int


class ScheduleShiftOut(BaseModel):
    """One upcoming shift on the organiser schedule view. ``assignee_name``
    is the volunteer's pseudonym (NULL for an open/unassigned shift)."""

    id: str
    chore_id: str
    chore_name: str
    on_date: date
    slot_index: int
    status: str
    assignee_name: str | None


class ScheduleStatsOut(BaseModel):
    scheduled: int
    done: int
    missed: int
    open: int


class ScheduleOut(BaseModel):
    """Organiser schedule: lifetime completion counts + upcoming shifts."""

    stats: ScheduleStatsOut
    upcoming: list[ScheduleShiftOut] = Field(default_factory=list)
