from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TenantMixin, TimestampMixin, UUIDMixin


class FeedbackToken(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One-time link between an email recipient and the
    questionnaire.

    Minted by the feedback worker before the email goes out,
    deleted on redemption. The token row never references a
    signup — the privacy contract forbids linking a response back
    to the attendee who gave it, and the dispatch / token / response
    chain reflects that physically: an event has tokens, an event
    has responses, neither knows about any signup.
    """

    __tablename__ = "feedback_tokens"

    # URL-safe token (secrets.token_urlsafe(32), ~43 chars). Looked up
    # directly from the link in the email.
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    # Feedback is per occurrence (one questionnaire after each date), so the
    # token and its responses hang off the occurrence, not the event.
    occurrence_id: Mapped[str] = mapped_column(
        Text, ForeignKey("occurrences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeedbackResponse(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """A single answer. Multiple rows per submission, one per
    answered question. Tied to the event only — never to the
    signup or the token that authorised it.

    ``question_key`` is the stable identifier of the question
    (e.g. ``"q1_overall"``); the questions themselves are
    Python constants in ``services.feedback_questions``, not DB
    rows. There's no FK to police it because there's no table to
    point at; the API submit handler validates against the
    in-memory constant set.
    """

    __tablename__ = "feedback_responses"

    occurrence_id: Mapped[str] = mapped_column(
        Text, ForeignKey("occurrences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Random per-submission id (not linked to anything else). Lets us
    # count distinct submissions ("12 people responded") without
    # storing a back-reference to the signup.
    submission_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    answer_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
