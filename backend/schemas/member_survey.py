from datetime import datetime

from pydantic import BaseModel, Field


class MemberSurveyFormOut(BaseModel):
    """Public structure of the new-members survey form. The client
    resolves all prompts and labels via i18n keyed off ``barriers``;
    the server only enumerates which barrier identifiers are valid."""

    barriers: list[str]


class MemberSurveySubmitIn(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    q1_connected: int = Field(ge=1, le=5)
    q2_clarity: int = Field(ge=1, le=5)
    q3_likelihood: int = Field(ge=1, le=5)
    q4_barriers: list[str] = Field(default_factory=list, max_length=20)
    q4_other_text: str | None = Field(default=None, max_length=500)
    q5_helps: str | None = Field(default=None, max_length=2000)


class MemberSurveyResponseOut(BaseModel):
    """One response row as the admin results page consumes it."""

    id: str
    created_at: datetime
    first_name: str | None
    q1_connected: int
    q2_clarity: int
    q3_likelihood: int
    q4_barriers: list[str]
    q4_other_text: str | None
    q5_helps: str | None
    model_config = {"from_attributes": True}


class RatingBreakdown(BaseModel):
    average: float | None
    distribution: list[int]  # length 5: counts for ratings 1..5


class MemberSurveyResultsOut(BaseModel):
    response_count: int
    q1_connected: RatingBreakdown
    q2_clarity: RatingBreakdown
    q3_likelihood: RatingBreakdown
    barrier_counts: dict[str, int]  # barrier_key -> count
    responses: list[MemberSurveyResponseOut]
