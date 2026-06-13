"""Standalone questionnaires — the "Forms" feature.

A ``Form`` is an organiser-authored questionnaire that lives
independently of any event: chapter-scoped (like Events), publicly
fillable by anyone with the slug (like the public event sign-up
page), no relationship to ``Event`` / ``Signup`` / the post-event
feedback flow. Forms get their own four-page organiser
experience (active list, archive list, details, edit) on top of
the page shells extracted in the previous phase.

Three tables:

* ``forms`` — one row per questionnaire. ``archived_at`` for soft
  archive (mirrors Event); a fresh slug per form makes the public
  URL bookmark-stable across restores.
* ``form_questions`` — per-form question list, ordered. Five
  kinds: ``rating``, ``text``, ``short_text``, ``single_choice``,
  ``multi_choice``. The kind enum is enforced at the schema layer
  and the public submit handler — adding a sixth requires
  touching both.
* ``form_responses`` — one row per (submission, question). The
  random ``submission_id`` groups answers from one fill-out into
  one logical submission, with no link back to whoever sent it
  (privacy contract: knowing the slug grants permission to
  submit; nothing in the system maps a response back to a
  specific person).
"""

from datetime import datetime
from typing import Literal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Form(UUIDMixin, TimestampMixin, Base):
    """One questionnaire. ``archived_at`` flips for archive/restore;
    edits overwrite in place. The slug is unique across the table
    and stays attached to the row across archive/restore so a
    bookmarked URL keeps resolving after a restore (the public
    surface 410s while archived — same model as Event)."""

    __tablename__ = "forms"

    # 8-char nanoid, public. Unique across all forms; archive
    # doesn't free it because the slug may be in URLs the user
    # bookmarked, and restoring expects the slug to come back
    # unchanged.
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # ISO language tag — drives the public form's UI language.
    # Two-letter codes only today; widen the Literal to add a region.
    locale: Mapped[Literal["nl", "en"]] = mapped_column(Text, nullable=False, default="nl")
    created_by: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    chapter_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Mirrors the events index — list queries filter on
    # ``archived_at IS NULL`` and ``chapter_id IN (...)`` together.
    __table_args__ = (Index("ix_forms_archived_chapter", "archived_at", "chapter_id"),)


class FormQuestion(UUIDMixin, TimestampMixin, Base):
    """One question on one form. ``ordinal`` drives display order
    (re-numbered 1..N on every update from the input order; the
    client doesn't have to send dense ordinals). ``options`` is
    only meaningful for the two choice kinds; ``low_label`` /
    ``high_label`` only for rating."""

    __tablename__ = "form_questions"

    form_id: Mapped[str] = mapped_column(Text, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # One of ``rating`` / ``text`` / ``short_text`` / ``single_choice``
    # / ``multi_choice``. Validated at the schema layer.
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    low_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    high_label: Mapped[str | None] = mapped_column(Text, nullable=True)

    # DB-level backstop for the kind vocabulary. The canonical set
    # is the ``QuestionKind`` literal in ``schemas/forms.py`` (the
    # API contract); this constraint makes a malformed row
    # unrepresentable even if a write path ever skipped the
    # schema-layer validation. Keep the two in sync when adding a
    # kind — the schema-drift CI gate doesn't cover this CHECK.
    __table_args__ = (
        CheckConstraint(
            "kind IN ('rating', 'text', 'short_text', 'single_choice', 'multi_choice')",
            name="ck_form_questions_kind",
        ),
    )


class FormResponse(UUIDMixin, TimestampMixin, Base):
    """One answer. Multiple rows per submission, one per answered
    question. Tied to the form only — never to the submitter.

    ``submission_id`` is a random per-submission token that groups
    the rows for one fill-out together. Nothing maps it back to a
    person; knowing the slug grants permission to submit, and the
    server stores no identifier beyond what the questions
    themselves collect.

    Cascades on form_id and question_id both: deleting a form
    deletes its responses; an organiser dropping a question
    deletes the responses to it (organiser opts in to that by
    deleting)."""

    __tablename__ = "form_responses"

    form_id: Mapped[str] = mapped_column(Text, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("form_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    answer_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of chosen option strings. ``single_choice`` carries
    # a one-element list; ``multi_choice`` carries the full subset.
    answer_choices: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
