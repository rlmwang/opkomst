# Design: quizzes, and a number question for both

Status: built. The order of work at the bottom is done, step by step.

Two things stayed out, as designed: partial credit on multi-choice, and
correctness revealed *during* the walk. The result screen does name the
right answer per question, and an organiser can switch that off
(``reveal_answers``); what is not built is telling somebody they were
right before the quiz is over, because doing that honestly costs a
round-trip per question and doing it cheaply means shipping the key.

One thing the design did not anticipate: the app has three landing
pages, not one, and the fifth tile belongs on all of them (the
signed-out root, the signed-in home, and the workspace menu).

A quiz is a questionnaire with a right answer. An organiser writes the
questions and the answers, a visitor answers them one at a time, and at
the end sees how they did. The organiser sees the same details page
they get for a form, plus what everybody scored.

That description is doing a lot of work in this document, because it
says the quiz is not a new thing that happens to look like a form. It
is a form with three additions (a key, a score, a different way of
walking through the questions) and one subtraction (you cannot change
your answers after you have seen the score).

This document is in five parts: where the data lives, the number
question kind that both products get, what a quiz does that a form does
not, what the fifth entity costs in surface area, and what this
deliberately leaves out.

---

## Part 1: where the data lives

### 1.1 The decision

**Quizzes and forms share the three tables that already exist**, with a
`mode` discriminator on the parent row. `forms.mode` is `'survey'` or
`'quiz'`.

The alternative is four new tables (`quizzes`, `quiz_questions`,
`quiz_submissions`, `quiz_responses`) mirroring the existing four. It
is worth naming what that costs, because "a quiz is its own entity" is
the intuitive answer and it is the expensive one:

| Concern | Shared tables | Separate tables |
|---|---|---|
| Question kinds | One `kind` vocabulary, one CHECK, one editor | Two of each, kept in step by hand |
| Adding the number kind | One place | Two places, on the day it is added and on every day after |
| `apply_questions` diff-apply | Reused as-is | Cloned, ~90 lines of ordinal juggling |
| Aggregates, CSV, submission reads | Reused | Cloned, ~200 lines |
| Public renderers | One per kind | Two per kind, drifting |
| Cost of the discriminator | Every `Form` query must filter on `mode` | None |

The last row is the real cost and it is a sharp one: a query that
forgets the filter puts quizzes in the forms list. Part 1.4 says how
that is prevented rather than hoped for.

The tables keep the name `forms`. Renaming them to something neutral
(`question_sets`) would describe the storage better and would touch
every file that says `Form` for no behaviour change. The API is the
contract that matters, and it says `/api/v1/quizzes`.

### 1.2 Columns

```
forms
  mode          text not null default 'survey'   -- NEW: 'survey' | 'quiz', CHECK
  reveal_answers boolean not null default true   -- NEW: quiz only, show the key on the result screen

form_questions
  points        integer not null default 0       -- NEW: what a correct answer is worth, 0 = not scored
  correct_int   integer null                     -- NEW: the key for rating / number
  correct_text  text null                        -- NEW: the key for short_text
  correct_choices json null                      -- NEW: the key for single_choice / multi_choice
  tolerance     integer null                     -- NEW: number only, accept within plus or minus n
  min_value     integer null                     -- NEW: number only, lower bound
  max_value     integer null                     -- NEW: number only, upper bound
  unit          text null                        -- NEW: number only, short label ("jaar", "km")

form_submissions
  score         integer null                     -- NEW: points earned, null on a survey
  max_score     integer null                     -- NEW: points available at submit time

form_responses
  awarded       integer null                     -- NEW: what this answer earned, null on a survey
```

Three of those deserve their reasons written down.

**`max_score` is stored, not computed.** An organiser can edit a quiz
after people have taken it: add a question, change what one is worth.
A stored score of 7 means nothing if the total silently moved from 10
to 20. Storing both makes an old result readable forever, which is the
same reason feedback answers carry no link back to a signup: the record
has to survive the thing it came from changing.

**`awarded` is stored per answer** for the same reason, one level down.
The result screen and the organiser's table both say "this answer
earned 2 of 3", and neither has to re-grade against a key that has
moved since.

**`points` defaults to 0, not 1.** A survey's questions are worth
nothing and always will be, so the default that is correct for the
common row is the one that also makes an unscored quiz question
expressible without a second flag.

### 1.3 The answer key, per kind

| Kind | Key | Correct when |
|---|---|---|
| `short_text` | `correct_text` | Case-folded, whitespace-collapsed exact match |
| `single_choice` | `correct_choices` (one) | The chosen option is the one |
| `multi_choice` | `correct_choices` (n) | The chosen set equals the key set exactly, no partial credit |
| `number` | `correct_int` plus optional `tolerance` | Within plus or minus tolerance, 0 by default |
| `rating` | `correct_int` | Equal |
| `text` | none | Never scored: `points` is forced to 0 |

`text` is the long free-form kind, and no rule can grade it. Rather
than forbid it in a quiz, it is allowed and always worth zero, which is
how "explain your answer" stays possible without inventing manual
grading. `apply_questions` already normalises fields per kind (it drops
the scale labels off a non-rating question); forcing `points = 0` on a
`text` question is one more line in the same loop, in the same place.

No partial credit on `multi_choice` in this version. Partial credit
needs a rule for wrong extras (does picking all five options score
three out of three?), and every rule for that is arguable. Exact-set is
the one nobody has to explain.

### 1.4 Keeping quizzes out of the forms list

Every existing read of `Form` becomes wrong the day this ships, in a
way that is invisible until an organiser sees a quiz in their forms
list. Two things stop that:

1. **One helper.** `services/forms.py` grows
   `query(db, mode)`, and every read goes through it. It is the only
   place `db.query(Form)` appears.
2. **A test that greps for the rest.** `tests/test_forms.py` scans the
   backend tree for `db.query(Form)` outside `services/forms.py` and
   fails on a hit. This is the mechanism
   `tests/test_privacy.py::test_decrypt_only_called_from_mail_lifecycle`
   already uses for the encryption boundary, and it is exactly as ugly
   and exactly as effective.

`access.py` (`get_form_for_user`, `form_scope_filter`) takes the mode
as a parameter for the same reason, so an organiser cannot reach a quiz
through a forms URL or the other way around.

---

## Part 2: the number question

This is independent of quizzes and worth shipping either way: a
questionnaire cannot currently ask how old somebody is, how many people
they are bringing, or what year they joined.

### 2.1 The kind

`kind = "number"`, sixth in the `QuestionKind` literal, the CHECK
constraint on `form_questions.kind`, and the editor's kind dropdown.
The literal in `schemas/forms.py` is the single source both the service
and the submit handler already read, so adding it there is most of the
work.

Per-question configuration: `min_value`, `max_value`, `unit`. All
optional. The bounds are validation, not decoration: the public page
refuses an out-of-range answer client-side and the submit handler
refuses it again server-side, because the first is a courtesy and the
second is the rule.

### 2.2 Integers only

Not decimals. An age, a headcount, a year and a distance in whole
kilometres are the questions people actually ask, and a decimal type
drags a rounding rule and a decimal separator (a Dutch visitor types
`1,5`, an English one types `1.5`) into every renderer, every CSV cell
and every aggregate. If a decimal question is ever genuinely wanted,
that is a `decimal` kind with its own column, not a widened `number`.

### 2.3 Where the answer goes

`form_responses.answer_int`, the column ratings already use. The
`answer_int: int | None = Field(ge=1, le=5)` bound on `FormAnswerIn`
comes off: 1 to 5 is a fact about ratings, not about integers, and it
belongs in the per-kind validation in `_build_submitted` where every
other kind's rule already lives. Rating keeps 1 to 5 there, and number
gets the question's own bounds.

### 2.4 What the organiser sees

`FormQuestionSummary` gains `number_count`, `number_average`,
`number_min`, `number_max`. No histogram: the buckets for an arbitrary
range are a choice with no obvious right answer, and four numbers
answer "what did people say" for an age or a headcount. The raw values
are in the CSV for anyone who wants to do better.

---

## Part 3: what a quiz does that a form does not

### 3.1 One question at a time

A new mini-app at `/q/{slug}`, its own Vite entry (`public-quiz.html`,
`src/public_quiz/`), on the same roughly 30KB budget as the other four.

The reuse that makes this cheap is one extraction:
**`public_shared/QuestionField.vue`**, lifted out of the `v-if` chain
in `PublicForm.vue`. It renders one question by kind and takes a
`v-model` on the answer shape. `PublicForm` loops over it; `PublicQuiz`
renders one of them at a time. The number kind is then implemented
once, and the next kind after that is too.

The walk itself:

- Progress as text, "vraag 3 van 10", not a bar. The count is the
  useful part and a bar is a decoration that has to be styled in two
  brands.
- Next and Back. You can change an answer until you submit, because
  this is a quiz at a party, not an exam, and locking answers would
  need per-question submits for no gain.
- Required questions gate Next, the same rule the form applies at
  submit, just earlier.
- One POST at the end, the same `FormSubmitIn` shape, the same
  endpoint pattern. Nothing is scored until then.

### 3.2 No answer key in the browser

The key never reaches the client before the submit. `PublicQuizOut`
carries prompts, options and bounds, and no `correct_*` field. Grading
happens in the submit handler, from the stored rows.

This is why there is no per-question "correct!" reveal in this version.
Doing it honestly costs a round-trip per question and a way to stop
somebody replaying the same question until it goes green; doing it
cheaply means shipping the key, which is a quiz solved by view-source.

### 3.3 The result screen

The submit response carries what the browser was never given:

```
QuizResultOut
  score          int
  max_score      int
  answers        [{question_id, awarded, points, correct_*}]   -- key included, now
  result_url     str
```

Rendered as the score, then the list of questions with what you said
and what was right, when `reveal_answers` is on. An organiser running
the same quiz twice in one evening turns it off.

### 3.4 The edit link becomes a result link

A form hands back an edit token so a respondent can fix an answer.
Editing a quiz answer after seeing the score is not a fix, it is a
second attempt with the answers in hand.

So the token opens a read-only page: your answers, what was right, your
score. Same `EditTokenMixin`, same organiser-side link recovery, same
`link_recovered_at` notice. `PATCH` on a quiz submission does not
exist. `DELETE` does: "remove my submission" is a privacy right and
withdrawing costs the withdrawer their score, so it is no loophole.

### 3.5 The organiser's details page

`FormDetailsPage` already renders per-question aggregates and a
submission list with a CSV export. A quiz gets the same page with three
additions:

- **Score column** in the submission list, `7 / 10`, sortable.
- **Average and best** above it. Not a distribution histogram, for the
  reason in 2.4.
- **Per-question difficulty**: the share of submissions that got it
  right, which is the one aggregate a quiz has that a survey cannot,
  and the one that tells an organiser which question was broken.

The CSV gains `score`, `max_score`, and a points column per question
beside the answer column.

---

## Part 4: the fifth entity, in full

None of this is interesting and all of it is required. The list is here
so the work is not discovered one file at a time:

| Where | What |
|---|---|
| `services/slug.py` | `"quizzes"` in `RESERVED_SLUGS` |
| `routers/spa.py` | `"q"` in `_PUBLIC_RESOLVERS`, `/quizzes/new` in `_APP_PAGE_META` |
| `routers/ads_txt.py` | `/quizzes/new` in the sitemap |
| `models/traffic.py` | `create_quiz`, `public_quiz` in `SURFACES` |
| `services/limits.py` | a `quiz` kind: `Form` filtered to `mode='quiz'`, its own ceiling |
| `services/entities.py` | `create_quiz`, beside the four |
| `routers/start.py` | `POST /api/v1/start/quizzes` |
| `routers/quizzes.py` | organiser CRUD, `@limiter` on every mutator |
| `routers/quizzes_public.py` | by-slug, submit, result-by-token, withdraw, QR |
| `frontend` | `useQuizzes.ts` (a `createEntityCrud("quizzes")` call), list, archived, details and edit pages, `public-quiz.html`, `src/public_quiz/` |
| `locales/{nl,en}.json` | the strings |
| `alembic` | one revision, the columns in 1.2 |

Four of those pages are the existing form pages with the resource name
changed, which is what `createEntityCrud` and the page shells were
extracted for.

**The landing page becomes two columns and three rows.** Decided.
`docs/focus.md` made it four tiles in a 2x2 grid deliberately, and the
fifth goes below the other four rather than into a third column: the
grid is already two columns at every width (`PersonalIndexPage`), so
this is the existing rule continuing, not a new layout. The last tile
sits alone on its row, which is a gap and not a problem, and the two
alternatives are worse. Hiding quizzes behind the forms tile buries
them; reaching them only from the forms list makes them a sub-feature,
which contradicts everything above.

---

## Part 5: what this deliberately does not do

- **No timer.** A countdown per question changes what the product is
  and needs a server clock to mean anything.
- **No leaderboard with names.** The respondent identity is a
  self-chosen pseudonym, real or not, and a ranked list of pseudonyms
  invites people to put a real name in the box. The organiser sees the
  scores; the room does not.
- **No question bank or randomised order.** Ordinals are the order.
- **No manual grading of open answers.** `text` is worth zero and says
  so in the editor.
- **No images in questions.** Image hosting exists per entity, not per
  question, and a picture round is a bigger change than it looks.
- **No partial credit**, see 1.3.
- **No import from an existing form.** "Turn this questionnaire into a
  quiz" is one row's `mode` and a key per question, so it is easy
  later, and it is a second UI to explain now.

## Order of work

1. **Done.** The number kind, on forms alone. It ships on its own, is useful on
   its own, and forces the per-kind validation split in 2.3 that the
   quiz work then builds on.
2. **Done.** `QuestionField.vue` extracted, `PublicForm` switched to it. No
   behaviour change, and the diff is reviewable precisely because
   nothing else moves.
3. **Done.** The migration, the `mode` discriminator, the `query(db, mode)`
   helper and its grep test. Still no quizzes: forms behave exactly as
   before, now with the seam in place.
4. **Done.** The quiz backend: keys, grading, submit, result-by-token.
5. **Done.** The quiz organiser pages, which are the form pages parameterised.
6. **Done.** `public_quiz`, the one-at-a-time walk and the result screen.
7. **Done.** The fifth tile, once there is something behind it.
