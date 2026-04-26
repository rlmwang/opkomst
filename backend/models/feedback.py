from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class FeedbackQuestion(UUIDMixin, TimestampMixin, Base):
    """Fixed-set questionnaire — same five questions every event uses.

    No per-event overrides in v1. The point of the standardisation is
    to reduce organiser workload and keep stats comparable across
    events.
    """

    __tablename__ = "feedback_questions"

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # "rating" (1-5) or "text"
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # i18n key under feedback.questions.<key> in the locale files. The
    # prompt + endpoint labels live there, not in the DB, so copy
    # tweaks don't need a migration.
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FeedbackToken(UUIDMixin, TimestampMixin, Base):
    """One-time link between an email recipient and the questionnaire.

    Minted by the feedback worker before the email goes out, deleted on
    redemption. Once a token is gone, the system has no way to map a
    response back to the signup that generated it. That's the privacy
    contract.
    """

    __tablename__ = "feedback_tokens"

    # URL-safe token (secrets.token_urlsafe(32), ~43 chars). Looked up
    # directly from the link in the email.
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    signup_id: Mapped[str] = mapped_column(Text, ForeignKey("signups.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class FeedbackResponse(UUIDMixin, TimestampMixin, Base):
    """A single answer. Multiple rows per submission, one per answered
    question. Tied to the event only — never to the signup or the token
    that authorised it.
    """

    __tablename__ = "feedback_responses"

    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(Text, ForeignKey("feedback_questions.id"), nullable=False)
    # Random per-submission id (not linked to anything else). Lets us
    # count distinct submissions ("12 people responded") without
    # storing a back-reference to the signup.
    submission_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    answer_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
