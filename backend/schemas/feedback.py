from pydantic import BaseModel, Field


class FeedbackQuestionOut(BaseModel):
    """Question shape for the public form. The frontend resolves the
    prompt + labels from i18n using ``key``."""

    id: str
    ordinal: int
    kind: str  # "rating" | "text"
    key: str
    required: bool
    model_config = {"from_attributes": True}


class FeedbackFormOut(BaseModel):
    """Public payload for GET /feedback/{token} — what the questionnaire
    page renders. Includes minimal event context so the page can show
    the user which event they're giving feedback on."""

    event_name: str
    event_slug: str
    questions: list[FeedbackQuestionOut]


class FeedbackAnswerIn(BaseModel):
    question_id: str
    # Either an int (rating questions) or a string (text questions);
    # the server validates the value matches the question's kind.
    answer_int: int | None = Field(default=None, ge=1, le=5)
    answer_text: str | None = Field(default=None, max_length=1000)


class FeedbackSubmitIn(BaseModel):
    answers: list[FeedbackAnswerIn]


class FeedbackQuestionSummary(BaseModel):
    """Per-question aggregate. ``rating_distribution`` is a 1..5 array
    when kind=='rating' (counts at each scale point), or null. ``texts``
    is the list of free-text answers when kind=='text', or null."""

    question_id: str
    key: str
    kind: str
    response_count: int
    rating_distribution: list[int] | None = None
    rating_average: float | None = None
    texts: list[str] | None = None


class FeedbackSummaryOut(BaseModel):
    """Organiser-only feedback summary for an event."""

    submission_count: int
    signup_count: int
    response_rate: float  # submission_count / signup_count, 0 if no signups
    questions: list[FeedbackQuestionSummary]
