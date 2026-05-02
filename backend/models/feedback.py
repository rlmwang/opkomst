from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class FeedbackToken(UUIDMixin, TimestampMixin, Base):
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
    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeedbackResponse(UUIDMixin, TimestampMixin, Base):
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

    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Random per-submission id (not linked to anything else). Lets us
    # count distinct submissions ("12 people responded") without
    # storing a back-reference to the signup.
    submission_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    answer_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
