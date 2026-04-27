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
    event_locale: str
    questions: list[FeedbackQuestionOut]


class FeedbackAnswerIn(BaseModel):
    question_id: str
    # Either an int (rating questions) or a string (text questions);
    # the server validates the value matches the question's kind.
    answer_int: int | None = Field(default=None, ge=1, le=5)
    answer_text: str | None = Field(default=None, max_length=500)


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


class EmailHealthOut(BaseModel):
    """Aggregate of feedback-email delivery status across an event's
    signups. Counts always sum to ``signup_count``."""

    not_applicable: int  # no email supplied / questionnaire disabled
    pending: int  # email collected, worker hasn't run yet
    sent: int  # SMTP accepted; no bounce reported
    bounced: int  # provider reported a hard bounce
    complaint: int  # recipient flagged as spam
    failed: int  # decrypt / SMTP send failure


class FeedbackSummaryOut(BaseModel):
    """Organiser-only feedback summary for an event."""

    submission_count: int
    signup_count: int
    response_rate: float  # submission_count / signup_count, 0 if no signups
    email_health: EmailHealthOut
    questions: list[FeedbackQuestionSummary]


class FeedbackSubmissionOut(BaseModel):
    """One submission as a flat record — keyed by ``question.key`` so
    a CSV consumer can map columns by question identifier without
    needing the questions table. Rating values surface as the int;
    text answers as the string. Missing answers are absent from
    ``answers``. ``submission_id`` is the random per-submission id
    that has no link back to a signup (privacy contract)."""

    submission_id: str
    answers: dict[str, int | str]
