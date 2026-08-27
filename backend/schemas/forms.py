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

# The three products the forms tables carry. A survey collects answers,
# a quiz grades them (``docs/design-quizzes.md``), a kompas points them
# (``docs/design-kompas.md``). Every read of the table names one, which
# is what keeps them out of each other's lists.
FormMode = Literal["survey", "quiz", "compass"]

# One of two axes and a direction along it: the whole of what a kompas
# adds to a question. ``low`` is the negative direction, drawn left and
# bottom.
Pole = Literal["x_low", "x_high", "y_low", "y_high"]
Axis = Literal["x", "y"]


class CompassAxisIn(BaseModel):
    """One axis on the create / update payload. Both are always sent:
    a kompas with one axis is not a kompas, and the server refuses a
    payload that says otherwise (``services/compass.validate_axes``).

    Single-language, in the form's own locale, exactly like a question
    prompt — the bilingual pair stops at the entity spine."""

    axis: Axis
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    # A name per side and nothing more: the axis's own description says
    # what the whole line is about, and a description per side was six
    # boxes on the create page for four words.
    low_name: str = Field(min_length=1, max_length=80)
    high_name: str = Field(min_length=1, max_length=80)


class CompassAxisOut(BaseModel):
    """An axis on the wire. Not a secret: what the two axes are called
    is the description of the kompas, and it is on the cover before
    anybody answers. Which option points where is the part that waits
    for the result (``PublicQuestionOut``)."""

    axis: str
    name: str
    description: str | None = None
    low_name: str
    high_name: str
    model_config = {"from_attributes": True}


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
    # ``step`` is what an answer has to land on: 5 accepts 0, 5, 10,
    # counted from ``min_value`` when there is one.
    min_value: int | None = None
    max_value: int | None = None
    step: int | None = Field(default=None, ge=1)
    # Quiz only; the service drops them on a survey. ``points`` is what
    # a correct answer earns, and one of the ``correct_*`` fields is the
    # key, depending on the kind. Null means "not said", which on a quiz
    # is one point: questions are worth the same until somebody decides
    # otherwise, and a quiz where every question is worth nothing is
    # nobody's intention.
    points: int | None = Field(default=None, ge=0, le=100)
    correct_int: int | None = None
    correct_text: str | None = Field(default=None, max_length=200)
    correct_choices: list[str] | None = Field(default=None, max_length=50)
    tolerance: int | None = Field(default=None, ge=0)
    # Kompas only; the service drops both on the other two products.
    # A rating poles the statement (``pole``, the side a 5 means); a
    # choice poles each option (``option_poles``, parallel to
    # ``options``, same length).
    pole: Pole | None = None
    option_poles: list[Pole] | None = Field(default=None, max_length=50)


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
    step: int | None = None
    # The key. Organiser-side only: it is what they typed, and it is
    # what the edit page has to show them again.
    points: int = 0
    correct_int: int | None = None
    correct_text: str | None = None
    correct_choices: list[str] | None = None
    tolerance: int | None = None
    # The directions. Organiser-side only, for the same reason the key
    # is: it is what they chose, and the edit page has to show it back.
    pole: str | None = None
    option_poles: list[str] | None = None
    model_config = {"from_attributes": True}


class PublicQuestionOut(BaseModel):
    """What a respondent's browser is allowed to know about a question.

    Everything ``FormQuestionOut`` has except the answer key and the
    directions. This is the one class standing between a quiz and being
    solved by view-source, and between a kompas and being answered by
    reading which button moves you where, so it lists its fields rather
    than excluding: a field added to the question model does not
    silently appear here."""

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
    step: int | None = None
    # How far off an answer may be and still count. Not the key: it is
    # the rule the question is marked by, and a guess-the-number
    # question that hides its own margin is asking people to guess the
    # rules as well as the answer.
    tolerance: int | None = None
    # What it is worth is not a secret, and on a quiz it is worth
    # knowing before you answer.
    points: int = 0
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
    # Quiz only: whether the result screen names the right answers or
    # only gives the score. Ignored on a survey, which has no answers to
    # reveal.
    reveal_answers: bool = True
    # Whether somebody may reopen their own link and change what they
    # said. A quiz never offers it, so the flag sits unread there.
    answers_editable: bool = True
    # Whether the public page insists on a (pseudo)name. Off by default
    # (``docs/design-public-pages-ux.md``): a name real or not is what
    # the contract offers, so an empty box is an answer.
    name_required: bool = False
    # Kompas only: the two axes and their four sides, dropped on the
    # other two products. A save always carries at least one question
    # (``services/forms._validate_questions``), and a question points
    # at an axis, so in practice a kompas save always carries both.
    axes: list[CompassAxisIn] = Field(default_factory=list, max_length=2)
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
    mode: FormMode
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
    reveal_answers: bool = True
    answers_editable: bool = True
    name_required: bool = False
    axes: list[CompassAxisOut] = Field(default_factory=list)
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
    mode: FormMode
    # Whether this page insists on a (pseudo)name, and whether somebody
    # who has answered may come back and change it.
    name_required: bool
    answers_editable: bool
    # A kompas says what it places you on before you answer; the other
    # two products send an empty list.
    axes: list[CompassAxisOut] = Field(default_factory=list)
    questions: list[PublicQuestionOut]


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


class QuizAnswerResult(BaseModel):
    """One graded answer on the result screen. The key is here and
    nowhere earlier: this shape is the response to the submit, so it
    arrives once the answering is over."""

    question_id: str
    awarded: int
    points: int
    correct: bool
    # What this person answered, in the kind's own shape. This is what
    # is stored; everything else on this shape is derived from it.
    given_int: int | None = None
    given_text: str | None = None
    given_choices: list[str] | None = None
    # What the right answer was, in the same shapes. Null when the quiz
    # is set not to reveal answers.
    correct_int: int | None = None
    correct_text: str | None = None
    correct_choices: list[str] | None = None


class QuizResultOut(BaseModel):
    """What a respondent sees when they finish: the score, the total
    that score was out of, and the per-question breakdown. ``edit_token``
    opens the same result again later, read-only: changing an answer
    after seeing the score is a second attempt, not a correction
    (``docs/design-quizzes.md`` part 3)."""

    submission_id: str
    edit_token: str
    score: int
    max_score: int
    reveal_answers: bool
    answers: list[QuizAnswerResult]


class CompassPoint(BaseModel):
    """One dot on the map. The only identifier is the self-chosen
    pseudonym, which is why the cover page says the name is going here
    before it asks for one (``docs/design-kompas.md`` 5.1). ``None`` is
    somebody who left the box empty, and their dot counts like anyone
    else's.

    No submission id: knowing which opaque id is which dot buys a
    reader nothing and costs the pseudonymity that the rest of the app
    keeps."""

    name: str | None = None
    x: float
    y: float
    # True on the dot belonging to whoever is reading. Absent from the
    # organiser's copy, where nobody is "you".
    you: bool = False


class CompassAnswerResult(BaseModel):
    """One answered question on the result screen, with the direction
    that was hidden until now. The page already has the prompt and the
    options from the walk, so this carries what it did not have."""

    question_id: str
    kind: str
    # The question's own direction, on a rating: the side a 5 meant.
    pole: str | None = None
    # One per option, in the options' own order, on a choice.
    option_poles: list[str] | None = None
    given_int: int | None = None
    given_choices: list[str] | None = None
    # What this answer was worth, on the axis it spoke to. Null when it
    # said nothing (skipped, or a question with no direction on it).
    axis: str | None = None
    value: float | None = None


class CompassAxisSummary(BaseModel):
    """One axis, and where the room sits on it. Read by the organiser's
    page and by every respondent's result, so the two cannot disagree. The three numbers are null before anybody has
    filled it in.

    ``ci_low`` / ``ci_high`` are the ends of the 95% confidence interval
    around ``average``, not the lowest and highest anybody scored: the
    question the page answers is where the room sits, and the interval
    is what says how sure that is (``services/compass.axis_stats``)."""

    axis: CompassAxisOut
    average: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class CompassResultOut(BaseModel):
    """What a respondent sees when they finish: where they landed, the
    room around them, and every answer with the direction it carried.

    ``edit_token`` opens the same result again later and, unlike a
    quiz, still opens the answers for editing: changing your mind after
    seeing the map is not a second attempt (``docs/design-kompas.md``
    5.4)."""

    submission_id: str
    edit_token: str
    # The pseudonym on the map, so the edit flow can put it back in the
    # box it came from.
    display_name: str | None = None
    # Non-NULL = an organiser has copied this submission's secret link
    # at least once, the same permanent notice the questionnaire's edit
    # page carries.
    link_recovered_at: datetime | None = None
    x: float
    y: float
    # How many answers spoke to each axis. Zero is the difference
    # between "your answers balanced" and "you said nothing about
    # this", and the screen says which.
    counted_x: int
    counted_y: int
    # The axes, each with where the room sits on it: the reader's own
    # marker is drawn against that band, which is what turns "you are
    # here" into "you are here, and this is where everyone else is".
    axes: list[CompassAxisSummary]
    answers: list[CompassAnswerResult]
    # Everybody, including this submission. Derived on every read, so a
    # reopened result shows the room as it stands rather than as it was.
    points: list[CompassPoint]


class CompassSummary(BaseModel):
    """The kompas half of the summary endpoint. Null on the other two
    products, which have no map."""

    axes: list[CompassAxisSummary]
    points: list[CompassPoint]


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


class NumberBucket(BaseModel):
    """One bar of a number question's histogram. ``label`` is what the
    axis says: a value when the bars are one per number, a range when
    they are binned."""

    label: str
    count: int


class FormQuestionSummary(BaseModel):
    """Per-question aggregate on the organiser details page.
    Shape mirrors the post-event feedback summary:

    * ``rating`` — ``rating_distribution`` (5-bucket counts) +
      ``rating_average``.
    * ``text`` / ``short_text`` — ``texts`` (newest first).
    * ``single_choice`` / ``multi_choice`` — ``choice_counts``
      keyed by option string.
    * ``number`` — ``number_average`` with the range people used, and
      ``number_buckets``, the histogram (``services/numbers``).
    """

    id: str
    ordinal: int
    kind: str
    prompt: str
    response_count: int
    # Quiz only: the share of answers that earned full marks, which is
    # the one aggregate a quiz has that a survey cannot, and the one
    # that says which question was broken.
    correct_share: float | None = None
    # Kompas only: which way this question pushed. A rating carries the
    # side a 5 meant; a choice carries one per option, in ``options``
    # order, so a count can be read next to the direction that earned
    # it (``docs/design-kompas.md`` 4.5).
    pole: str | None = None
    option_poles: list[str] | None = None
    rating_distribution: list[int] | None = None
    rating_average: float | None = None
    texts: list[str] | None = None
    choice_counts: dict[str, int] | None = None
    number_average: float | None = None
    number_min: int | None = None
    number_max: int | None = None
    number_buckets: list[NumberBucket] | None = None


class FormSummaryOut(BaseModel):
    """Organiser summary endpoint. ``submission_count`` is the
    number of distinct fill-outs; per-question aggregates explain
    what each question collected. The three score fields are null on a
    survey, which has no score."""

    submission_count: int
    score_average: float | None = None
    score_best: int | None = None
    max_score: int | None = None
    # Null on the two products that do not place anybody.
    compass: CompassSummary | None = None
    questions: list[FormQuestionSummary]


class QuizSubmissionOut(BaseModel):
    """One taken quiz, for the organiser's list. Same privacy contract
    as the survey row: the id is opaque and the pseudonym is the only
    identifier."""

    submission_id: str
    display_name: str | None
    created_at: datetime
    score: int
    max_score: int
    answers: dict[str, int | str | list[str]]
    link_recovered_at: datetime | None = None


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
    # Where this submission landed, on a kompas. Two more CSV columns,
    # null on the other two products.
    x: float | None = None
    y: float | None = None
    # Non-NULL = an organiser recovered this submission's edit link.
    link_recovered_at: datetime | None = None
