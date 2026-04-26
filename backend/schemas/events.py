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
    questionnaire_enabled: bool = True

    @field_validator("source_options")
    @classmethod
    def _validate_source_options(cls, v: list[str]) -> list[str]:
        cleaned = [opt.strip() for opt in v if opt.strip()]
        if not cleaned:
            raise ValueError("At least one source option is required")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Source options must be unique")
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
    questionnaire_enabled: bool
    afdeling_id: str | None
    afdeling_name: str | None
    signup_count: int  # aggregate party_size sum, not row count
    model_config = {"from_attributes": True}


class EventStatsOut(BaseModel):
    """Organiser-only aggregate. Never includes individual signups."""

    total_signups: int
    total_attendees: int  # sum of party_size
    by_source: dict[str, int]


class SignupCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    party_size: int = Field(ge=1, le=50)
    source_choice: str = Field(min_length=1)
    # Optional — when present, encrypted at rest and used once for the
    # feedback email. The form must surface a clear notice before this is shown.
    email: LowercaseEmail | None = None


class SignupAck(BaseModel):
    """Public response after a successful signup. Returns nothing
    identifying — just confirms the booking landed."""

    status: str = "ok"
