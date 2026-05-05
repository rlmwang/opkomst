from sqlalchemy import SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class MemberSurveyResponse(UUIDMixin, TimestampMixin, Base):
    """One submission of the new-members feedback survey.

    Self-contained: a single row carries every answer (no
    per-question row-per-answer shape, since the questionnaire is
    fixed and small). The six questions map to columns:

    * ``q1_connected`` / ``q2_clarity`` / ``q3_likelihood`` —
      1..5 ratings, required.
    * ``q4_barriers`` — multi-select against
      ``BARRIER_KEYS``; validated by the submit handler.
    * ``q4_other_text`` — free-text "anders, namelijk" addendum
      to Q4. Optional.
    * ``q5_helps`` — fully open Q5 answer. Optional.
    * ``q6_anything_else`` — fully open Q6 catch-all about the
      survey or the new-members day itself. Optional.

    Privacy: the form collects a first name (so an organiser can
    follow up with "Bob said he doesn't know where to start").
    No email, no chapter, no IP, no link to a User row. The
    first name is treated as a soft identifier — the public
    intro copy makes that explicit so respondents can choose to
    leave it blank or use an alias.
    """

    __tablename__ = "member_survey_responses"

    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    q1_connected: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    q2_clarity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    q3_likelihood: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    q4_barriers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    q4_other_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    q5_helps: Mapped[str | None] = mapped_column(Text, nullable=True)
    q6_anything_else: Mapped[str | None] = mapped_column(Text, nullable=True)
