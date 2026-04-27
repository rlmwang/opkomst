from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .common import LowercaseEmail


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    starts_at: datetime
    ends_at: datetime
    source_options: list[str] = Field(min_length=1)
    # Optional list of "I can help with" tasks. Defaults to empty —
    # an event with no help_options doesn't render the question on
    # the public form.
    help_options: list[str] = Field(default_factory=list)
    questionnaire_enabled: bool = True
    # Two-letter ISO language tag. Drives both the public sign-up
    # page's UI language and the locale of the feedback email sent
    # afterwards. Defaults to Dutch — the org's primary audience.
    locale: str = Field(default="nl", pattern="^(nl|en)$")

    @field_validator("source_options")
    @classmethod
    def _validate_source_options(cls, v: list[str]) -> list[str]:
        cleaned = [opt.strip() for opt in v if opt.strip()]
        if not cleaned:
            raise ValueError("At least one source option is required")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Source options must be unique")
        return cleaned

    @field_validator("help_options")
    @classmethod
    def _validate_help_options(cls, v: list[str]) -> list[str]:
        cleaned = [opt.strip() for opt in v if opt.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Help options must be unique")
        return cleaned


class EventOut(BaseModel):
    id: str
    slug: str
    name: str
    topic: str | None
    location: str
    latitude: float | None
    longitude: float | None
    starts_at: datetime
    ends_at: datetime
    source_options: list[str]
    help_options: list[str]
    questionnaire_enabled: bool
    locale: str
    chapter_id: str | None
    chapter_name: str | None
    signup_count: int  # aggregate party_size sum, not row count
    model_config = {"from_attributes": True}


class EventStatsOut(BaseModel):
    """Organiser-only aggregate. Never includes individual signups."""

    total_signups: int
    total_attendees: int  # sum of party_size
    by_source: dict[str, int]
    # How many signups opted into each help_option configured on
    # the event. Keys are exactly the strings on
    # ``Event.help_options``; values are headcounts of signups
    # whose ``help_choices`` includes that string. Sums can exceed
    # ``total_signups`` because each signup can pick multiple
    # options.
    by_help: dict[str, int]


class SignupSummaryOut(BaseModel):
    """A single signup as seen on the organiser's details page.
    Deliberately minimal — name and headcount only. Never email,
    source, or feedback-email status; those exist on the model but
    are private to the worker."""

    display_name: str | None
    party_size: int
    # Empty when the event had no help_options configured or the
    # signup skipped the question.
    help_choices: list[str]


class SignupCreate(BaseModel):
    # Only ``party_size`` is genuinely required — visitors can sign
    # up anonymously and skip the source question.
    display_name: str | None = Field(default=None, max_length=100)
    party_size: int = Field(ge=1, le=50)
    source_choice: str | None = None
    # Subset of the event's help_options the attendee opted into. Empty
    # is fine — the question is itself optional. The router validates
    # every choice against the parent event's configured options.
    help_choices: list[str] = Field(default_factory=list)
    # Optional — when present, encrypted at rest and used once for the
    # feedback email. The form must surface a clear notice before this is shown.
    email: LowercaseEmail | None = None

    @field_validator("help_choices")
    @classmethod
    def _validate_help_choices(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Help choices must be unique")
        return cleaned


class SignupAck(BaseModel):
    """Public response after a successful signup. Returns nothing
    identifying — just confirms the booking landed."""

    status: str = "ok"
