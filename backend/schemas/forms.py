"""Pydantic DTOs for the Forms feature.

Three concerns:

* Organiser-side CRUD payloads (``FormCreate`` / ``FormUpdate``)
  carry a full per-form question list — the server diff-applies
  on update.
* ``FormOut`` is what the organiser endpoints return: same fields
  as the create payload plus server-assigned ids and timestamps,
  the slug, and the archived flag.
* Public-side shapes — ``PublicFormOut`` (what
  ``/by-slug/{slug}`` renders), ``FormAnswerIn`` / ``FormSubmitIn``
  (what the public submit endpoint accepts), and the kind enum
  the public submit handler validates against.

The question kind enum is defined here and re-imported by the
service layer + submit handler — one source of truth for the
six supported kinds.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import BilingualTitleMixin, DisplayName, InstagramHandle, Locale, RichText

QuestionKind = Literal["rating", "text", "short_text", "single_choice", "multi_choice", "number"]


class FormQuestionIn(BaseModel):
    """One question on the create / update payload. ``id`` is null
    for newly-added rows; existing questions carry their server-
    assigned uuid so the diff-apply on update matches by id (and
    the row's responses stay attached across a prompt edit).
    ``ordinal`` is not on this shape — the server re-numbers from
    input order, which means reordering on the frontend is just
    "send back in the new order".
    """

    id: str | None = None
    kind: QuestionKind
    prompt: str = Field(min_length=1, max_length=500)
    required: bool = True
    options: list[str] = Field(default_factory=list, max_length=50)
    low_label: str | None = Field(default=None, max_length=80)
    high_label: str | None = Field(default=None, max_length=80)
    # ``number`` only; the service drops them on every other kind.
    min_value: int | None = None
    max_value: int | None = None
    unit: str | None = Field(default=None, max_length=20)


class FormQuestionOut(BaseModel):
    """Question shape on the wire. Organiser endpoints + the
    public-by-slug endpoint both return this; the public form
    renders ``prompt`` / ``options`` / ``low_label`` / ``high_label``
    verbatim. ``ordinal`` is server-assigned (1..N)."""

    id: str
    ordinal: int
    kind: str
    prompt: str
    required: bool
    options: list[str]
    low_label: str | None = None
    high_label: str | None = None
    min_value: int | None = None
    max_value: int | None = None
    unit: str | None = None
    model_config = {"from_attributes": True}


class FormCreate(BilingualTitleMixin):
    """Organiser create payload."""

    # See ``EventCreate.chapter_id``: required for an organisation,
    # ``None`` for a personal account, decided by the actor's tenant.
    chapter_id: str | None = None
    description_nl: RichText
    description_en: RichText
    image_artist_instagram: InstagramHandle
    locale: Locale = "nl"
    # Optional on create — an organiser can save a draft form with
    # no questions and add them on the edit page afterwards. On
    # update the same field is "the exact question set after the
    # save" (matched by id; null ids insert).
    questions: list[FormQuestionIn] = Field(default_factory=list)


class FormUpdate(FormCreate):
    """Same shape as create. Kept as a distinct class so the
    OpenAPI schema distinguishes the two endpoints even though
    the body is identical."""


class FormListOut(BaseModel):
    """Organiser list-row DTO. Carries only the scalar fields the
    active / archived list pages render — slug, chapter name, the
    archived flag, the timestamp they sort on. Deliberately omits
    the question list: a list of N forms would otherwise drag N
    question sets over the wire that the list view never shows
    (mirrors how ``EventOut`` carries ``attendee_count`` rather
    than the signup list)."""

    id: str
    slug: str
    name_nl: str | None
    name_en: str | None
    locale: Locale
    chapter_id: str | None
    chapter_name: str | None
    archived: bool
    created_at: datetime
    submission_count: int
    model_config = {"from_attributes": True}


class FormOut(FormListOut):
    """Single-form DTO. The list-row fields plus the description and
    the full question list, so the details / edit pages pre-populate
    without an extra round-trip."""

    description_nl: str | None = None
    description_en: str | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    questions: list[FormQuestionOut] = Field(default_factory=list)


class PublicFormOut(BaseModel):
    """What the public fill-out page (``/f/{slug}``) reads. No
    chapter id, no internal timestamps — just the form name +
    description + image + locale + questions in display order."""

    id: str
    name_nl: str | None
    name_en: str | None
    description_nl: str | None = None
    description_en: str | None = None
    image_url: str | None = None
    image_artist_instagram: str | None = None
    locale: Locale
    questions: list[FormQuestionOut]


class FormAnswerIn(BaseModel):
    """One answered question on the public submit payload. Exactly
    one answer-shaped field is meaningful per kind; the server
    validates the right field is populated against the question's
    stored kind, and ignores the others."""

    question_id: str
    # No range here. 1 to 5 is a fact about ratings, not about
    # integers, and a number question's bounds are its own. Both are
    # checked per kind in ``routers/forms_public._build_submitted``,
    # where every other kind's rule already lives.
    answer_int: int | None = None
    answer_text: str | None = Field(default=None, max_length=2000)
    answer_choices: list[str] | None = Field(default=None, max_length=50)


class FormSubmitIn(BaseModel):
    # Optional pseudonym (real or not), shared primitive — same
    # contract as the event sign-up name.
    display_name: DisplayName
    answers: list[FormAnswerIn]


class FormSubmitAck(BaseModel):
    """Public submit response. ``submission_id`` confirms the
    submission landed; ``edit_token`` is the secret edit-link token,
    returned once so the page can render the magic edit link (never
    stored raw, never recoverable)."""

    submission_id: str
    edit_token: str


class FormEditOut(BaseModel):
    """Current values of a submission, for pre-filling the edit form
    (reached via the edit-link token). ``answers`` keyed by question
    id — same shape as the CSV row's answers."""

    display_name: str | None
    answers: dict[str, int | str | list[str]]
    # Non-NULL = an organiser has copied this submission's secret link
    # at least once; drives the permanent notice banner on the edit page.
    link_recovered_at: datetime | None = None


class FormQuestionSummary(BaseModel):
    """Per-question aggregate on the organiser details page.
    Shape mirrors the post-event feedback summary:

    * ``rating`` — ``rating_distribution`` (5-bucket counts) +
      ``rating_average``.
    * ``text`` / ``short_text`` — ``texts`` (newest first).
    * ``single_choice`` / ``multi_choice`` — ``choice_counts``
      keyed by option string.
    * ``number`` — ``number_average`` with the range people used.
      No histogram: the buckets for an arbitrary range are a choice
      with no obvious right answer, and four numbers answer "what did
      people say" for an age or a headcount. The raw values are in
      the CSV for anyone who wants to do better.
    """

    id: str
    ordinal: int
    kind: str
    prompt: str
    response_count: int
    rating_distribution: list[int] | None = None
    rating_average: float | None = None
    texts: list[str] | None = None
    choice_counts: dict[str, int] | None = None
    number_average: float | None = None
    number_min: int | None = None
    number_max: int | None = None


class FormSummaryOut(BaseModel):
    """Organiser summary endpoint. ``submission_count`` is the
    number of distinct fill-outs; per-question aggregates explain
    what each question collected."""

    submission_count: int
    questions: list[FormQuestionSummary]


class FormSubmissionOut(BaseModel):
    """One submission as a flat row for the CSV export. ``answers``
    is keyed by question id; values match the kind: int for
    rating, string for text/short_text, list[str] for choice
    kinds. Missing answers are absent from the dict.

    ``submission_id`` is the random per-submission token with no
    link back to the submitter — same privacy contract as the
    post-event feedback CSV."""

    submission_id: str
    display_name: str | None
    created_at: datetime
    answers: dict[str, int | str | list[str]]
    # Non-NULL = an organiser recovered this submission's edit link.
    link_recovered_at: datetime | None = None
