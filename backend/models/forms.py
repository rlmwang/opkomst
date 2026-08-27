"""Standalone questionnaires — the "Forms" feature.

A ``Form`` is an organiser-authored questionnaire that lives
independently of any event: chapter-scoped (like Events), publicly
fillable by anyone with the slug (like the public event sign-up
page), no relationship to ``Event`` / ``Signup`` / the post-event
feedback flow. Forms get their own four-page organiser
experience (active list, archive list, details, edit) on top of
the page shells extracted in the previous phase.

Four tables:

* ``forms`` — one row per questionnaire. ``mode`` says which of the
  three products it is, ``survey``, ``quiz`` or ``compass``: they
  differ by what an answer means (nothing, a right answer, a
  direction) and by how the questions are walked through, and share
  everything else (``docs/design-quizzes.md``,
  ``docs/design-kompas.md``). ``archived_at`` for soft archive
  (mirrors Event); a fresh slug per form makes the public URL
  bookmark-stable across restores.
* ``form_questions`` — per-form question list, ordered. Six
  kinds: ``rating``, ``text``, ``short_text``, ``single_choice``,
  ``multi_choice``, ``number``. The kind enum is enforced at the
  schema layer and the public submit handler — adding a seventh
  requires touching both.
* ``form_questions`` also carries the quiz half of a question: what a
  correct answer is worth and what the correct answer is. Both are
  null-or-zero on a survey, dropped on write rather than trusted from
  the payload. Nothing stores a score: an answer plus the current key
  is the score (``services/quizzes``).
* ``form_questions`` carries the kompas half too: the direction an
  answer moves somebody in. A rating poles the statement (``pole``,
  the side a 5 means); a choice poles each option (``option_poles``,
  parallel to ``options``). Null on the other two products, and no
  position is stored anywhere: an answer plus the current poles is the
  position (``services/compass``).
* ``compass_axes`` — exactly two rows per kompas, in
  ``models/compass.py``: what the two axes are called and what each of
  their four sides stands for.
* ``form_responses`` — one row per (submission, question). The
  random ``submission_id`` groups answers from one fill-out into
  one logical submission, with no link back to whoever sent it
  (privacy contract: knowing the slug grants permission to
  submit; nothing in the system maps a response back to a
  specific person).
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import EditTokenMixin, OrgEntityMixin, TenantMixin, TimestampMixin, UUIDMixin


class Form(UUIDMixin, TimestampMixin, OrgEntityMixin, TenantMixin, Base):
    """One questionnaire, quiz or kompas, told apart by ``mode``.
    ``archived_at`` flips for archive/restore;
    edits overwrite in place. The slug is unique across the table
    and stays attached to the row across archive/restore so a
    bookmarked URL keeps resolving after a restore (the public
    surface 410s while archived — same model as Event)."""

    __tablename__ = "forms"

    # Spine (slug, name, image_url, image_artist_instagram, locale,
    # created_by, chapter_id, archived_at) comes from OrgEntityMixin.
    # ``survey``, ``quiz`` or ``compass``. Every read filters on it; the one place
    # that does is ``services/forms.query``, and a test greps for
    # anyone else querying this table.
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="survey", server_default="survey")
    # Optional blurb shown on the public page under the name — same
    # role as the event topic / datepoll description.
    description_nl: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quiz only: whether the result screen names the right answer per
    # question or only says the score. An organiser running the same
    # quiz twice in one evening turns it off.
    reveal_answers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Whether somebody who has answered may open their own link and
    # change what they said. A survey and a kompas are opinions, and an
    # opinion is allowed to change; an organiser closing a vote turns
    # this off. A quiz never offers it at all, score first and edit
    # after being the definition of cheating, so the column sits unread
    # on a quiz row (``docs/design-quizzes.md``).
    answers_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Whether the public page insists on a (pseudo)name before it will
    # accept anything. Off by default: a name real or not is what the
    # contract offers, and a page that refuses an empty box asks for an
    # identity the organiser may not need. On when the answers are only
    # useful attached to somebody.
    name_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Mirrors the events index — list queries filter on
    # ``archived_at IS NULL`` and ``chapter_id IN (...)`` together.
    __table_args__ = (
        # ``mode`` leads: every list query names it before it filters
        # anything else.
        Index("ix_forms_mode_archived_chapter", "mode", "archived_at", "chapter_id"),
        CheckConstraint("num_nonnulls(name_nl, name_en) >= 1", name="ck_forms_name_present"),
        CheckConstraint("mode IN ('survey', 'quiz', 'compass')", name="ck_forms_mode"),
    )


class FormQuestion(UUIDMixin, TimestampMixin, TenantMixin, Base):
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
    # ``number`` only, and all three are about which numbers count as
    # an answer: the bounds it has to sit between, and the step it has
    # to land on. ``step`` of 5 with a minimum of 0 accepts 0, 5, 10;
    # without a minimum it accepts any multiple of 5. The public page
    # says all of this above the box and the submit handler enforces
    # it, because the first is a courtesy and the second is the rule.
    min_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The quiz half. ``points`` is what a correct answer earns and
    # defaults to nothing, because a survey's questions are worth
    # nothing and always will be; a quiz question worth 0 is one that
    # is asked but not scored, which is how an open "why?" stays
    # possible without inventing manual grading. The key itself is one
    # of the three ``correct_*`` columns depending on the kind, and
    # ``tolerance`` widens a number's key into a range.
    #
    # None of this ever reaches a respondent's browser before they
    # submit (``schemas/forms.PublicQuestionOut``).
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    correct_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_choices: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tolerance: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The kompas half: which way an answer moves somebody. A pole is
    # one of ``x_low`` / ``x_high`` / ``y_low`` / ``y_high``, naming an
    # axis and a direction along it (``docs/design-kompas.md`` 1.4).
    #
    # Which thing carries it depends on the kind, because the two kinds
    # put the choice in different places. A ``rating`` poles the
    # statement: ``pole`` is the side a 5 means, a 1 is the other end
    # of the same axis and a 3 is the middle. A ``single_choice`` poles
    # each option: ``option_poles`` is index-parallel to ``options``,
    # same length, so renaming an option keeps its direction and the
    # options need not share an axis.
    #
    # Index-parallel rather than keyed by option text, which is what
    # ``correct_choices`` does: a key by string is right for a
    # reference into the options and wrong for an attribute of each of
    # them.
    #
    # Both are null on a survey and on a quiz, dropped on write rather
    # than trusted from the payload, and neither ever reaches a
    # respondent's browser before they submit
    # (``schemas/forms.PublicQuestionOut``): a kompas whose page says
    # which button moves you where is one people answer to land
    # somewhere.
    pole: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_poles: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # DB-level backstop for the kind vocabulary. The canonical set
    # is the ``QuestionKind`` literal in ``schemas/forms.py`` (the
    # API contract); this constraint makes a malformed row
    # unrepresentable even if a write path ever skipped the
    # schema-layer validation. Keep the two in sync when adding a
    # kind — the schema-drift CI gate doesn't cover this CHECK.
    __table_args__ = (
        CheckConstraint(
            "kind IN ('rating', 'text', 'short_text', 'single_choice', 'multi_choice', 'number')",
            name="ck_form_questions_kind",
        ),
    )


class FormSubmission(UUIDMixin, EditTokenMixin, TimestampMixin, TenantMixin, Base):
    """One fill-out. Holds the self-chosen pseudonym
    (``display_name``, NULL = anonymous) and groups the per-question
    answer rows. Same parent-submission shape as ``Signup`` /
    ``DatepollSubmission`` — the only respondent identifier is the
    pseudonym, real or not."""

    __tablename__ = "form_submissions"

    form_id: Mapped[str] = mapped_column(Text, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ``edit_token_hash`` + ``link_recovered_at`` come from EditTokenMixin.
    #
    # No score column: a score is what these answers are worth against
    # the quiz as it stands, computed on every read
    # (``services/quizzes.score_of``). Storing it would freeze it, and
    # an organiser who re-weights a question means the scores to move.


class FormResponse(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One answer — one row per answered question, FK'd to the parent
    ``form_submissions`` row that carries the pseudonym.

    Cascades on form_id and question_id both: deleting a form deletes
    its responses; an organiser dropping a question deletes the
    responses to it (organiser opts in to that by deleting)."""

    __tablename__ = "form_responses"

    form_id: Mapped[str] = mapped_column(Text, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("form_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of chosen option strings. ``single_choice`` carries
    # a one-element list; ``multi_choice`` carries the full subset.
    answer_choices: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
