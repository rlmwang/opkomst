from pydantic import BaseModel, Field

from ..models.tenants import AGENDA_WINDOW_MAX_DAYS, AGENDA_WINDOW_MIN_DAYS

_DAYS = Field(ge=AGENDA_WINDOW_MIN_DAYS, le=AGENDA_WINDOW_MAX_DAYS)


class TenantSettingsOut(BaseModel):
    """The organisation-wide settings an admin can change from inside
    the app. Today that is the public agenda's rolling window; the DTO
    is a container so the next one is a field rather than an endpoint."""

    agenda_future_days: int
    agenda_past_days: int
    model_config = {"from_attributes": True}


class TenantSettingsUpdate(BaseModel):
    """A full replacement, not a patch: two numbers on one form that is
    saved as a whole, so both always arrive. The bounds match the
    table's check constraints, which is what makes a 422 here rather
    than a 500 three frames later."""

    agenda_future_days: int = _DAYS
    agenda_past_days: int = _DAYS
