# Design: the kompas, our sixth item

Status: built. The order of work at the bottom is done, step by step.

Four things the design did not anticipate, all found by running it
rather than by reading it:

* **The client refused in the wrong order.** "Nobody can move on
  Economie" fired before "question 1 has no side yet", which is the
  same complaint one level too abstract and sends an organiser to the
  wrong end of the page. The server already ran them in the right
  order; the client now matches it (part 4.4).
* **Three CSS custom properties did not exist.** `--brand-accent`,
  `--brand-muted` and `--brand-accent-contrast` are not tokens any
  brand declares, so every rule reading them was dropped and the map's
  dots and the scale's picked number rendered with no background at
  all. `scripts/check_brand_tokens.py` now fails on a `var(--brand-…)`
  no brand defines, which found seven more of them on four pages that
  had nothing to do with this feature.
* **A missing copy key reached the page**, rendering as
  `[compasses.question.pickOptionPoles]`. The enumerating test in
  lesson 6 covered the four shared pages and not the components, so it
  now scans the whole tree for keys under the three product
  namespaces.
* **The answer-row grammar was not shared**, only duplicated: the quiz
  kept it in its own scoped block, so the kompas's result list arrived
  with none of it. It lives in `public_shared/forms.css` now, which is
  where part 5.3 said it already did.

One thing the design did anticipate and is worth naming: nothing about
the arithmetic changed between writing it down and running it. The
first end-to-end run of six real submissions matched the hand
calculation on every coordinate.

A kompas is a questionnaire that places you on a map. The organiser
asks two sorts of question and says, for each answer, which of two axes
it moves you along and in which direction. Somebody fills it in, sees
where they landed, and sees the rest of the room around them.

That description already says what this is not: it is not a quiz with
different scoring, and it is not a new questionnaire engine. It is the
`forms` table's third product, the same way a quiz is its second: one
new answer meaning (a direction instead of a key), one new derived
number (a coordinate instead of a score), one new picture (a scatter
instead of a histogram).

The concept comes from `../stemwijzer`, whose `KOMPAS.md` maps each
*question* to an axis and a direction, and whose `compute_axes` places
a point at the mean of `answer_value * direction` per axis. We keep
that arithmetic exactly and give it two ways in: a statement you rate,
which is stemwijzer's own shape, and a multiple-choice question where
each option carries its own direction, which is the shape stemwijzer
cannot express.

Seven parts: what the quiz taught us, where the data lives, what the
numbers are, what the organiser writes, what a respondent sees, what
the sixth item costs in surface area, and what stays out.

---

## Part 0: what the quiz got wrong, and what this does about it

`docs/design-quizzes.md` was a good design that needed four rounds of
correction after it shipped. Each correction is a rule here, written
before the code rather than after it.

**1. Derived, never stored.** The quiz design specified `score`,
`max_score` and `awarded` columns, and they were deleted again
(`2f795bf98301_scores_are_derived_not_stored`) because an organiser who
fixes a mis-typed key means every score to move with it. A kompas has
the same property and a sharper version of it: an organiser who moves
one answer from `x_low` to `y_high` means every dot on the map to move.
**No `x`, no `y`, no coordinate is stored anywhere.** A position is the
stored answers read against the kompas as it stands now, computed by
one function that both the respondent's screen and the organiser's page
call.

**2. The picture switches on what the question allows, not on what came
back.** The number histogram had to be rebuilt around this
(`services/numbers.py`): the axis is the same whether two people
answered or two hundred. **The scatter's domain is fixed at [-1, 1]**
in both directions, always, because that is the range a mean of
per-answer values in [-1, 1] can occupy. Stemwijzer's plot derives its
extent from the data (`Math.max(1, Math.ceil(max * 1.15))`); we do not,
because a map that rescales as people fill it in is a map where your
dot moves after you have seen it.

**3. The cover page is part of the product.** The quiz asked for a name
at the end, where it competed with the score, and had to be given a
cover: picture, title, description, privacy notice, name. A kompas
needs the cover more than a quiz does, because the name is going on a
chart other people will read, and the moment to say so is before the
box, not after the submit.

**4. The result redraws the question as it was asked.** A quiz result
that said "you: 3, right: 4" threw away what was asked and what could
have been answered. The kompas result redraws every question in its own
shape, the pick marked in place and the direction named beside it, so
the map has a visible reason.

**5. The organiser's page has to say what the answer meant.** The quiz
details page shipped without showing what the right answer was, and it
had to be added. Here that means every aggregate carries its direction:
an option's count says which pole those people moved toward, and a
statement's average says which pole the room leaned to.

**6. Enumerate the copy, do not spot it.** Eight strings showed through
from the questionnaire onto the quiz pages because the shared pages
fall back to `forms.*` when a `quizzes.*` key is missing (`e9dd24b`),
and the archived page is still resolving eight keys under a
`quizzes.archived.*` block that does not define them. The fallback
chain is about to get a third product and the same failure mode, so
this design does two things: it replaces the two-way `te()` check with
one `useFormText().L(key)` helper that takes the resource from the
route, and it adds a test that enumerates every key the four shared
pages resolve and refuses one that is neither on the shared list nor
defined by every product. Step 1 of the work, before any compass copy
exists, because it repays itself on the quiz immediately.

**7. Say the refusal before the request, in Dutch, naming the
question.** "Vraag 3: kies bij elk antwoord een kant van een as" and
not "opslaan ging mis". Part 4.4 enumerates every refusal.

**8. The tile goes on three landing pages, not one.** The signed-out
root (`PersonalIndexPage`), the signed-in home (`HomePage`) and the
workspace menu (`AppHeader`) each hold their own list, and the quiz
took two corrections to land in all three.

---

## Part 1: where the data lives

### 1.1 A third mode, not a fourth table set

`forms.mode` becomes `'survey' | 'quiz' | 'compass'`. The three share
`forms`, `form_questions`, `form_submissions` and `form_responses`, and
the whole of `docs/design-quizzes.md` Part 1.1 applies again: one kind
vocabulary, one diff-apply, one options list, one CSV, one editor, one
set of public renderers.

The reuse is larger than it was for the quiz, because the seams the
quiz needed were built once and are parameterised already:

| Seam | What the compass passes |
|---|---|
| `services/forms.query(db, mode)` | `'compass'`, and `tests/test_form_modes.py` still greps for anyone reading the table elsewhere |
| `routers/forms.build_router` | a third mount at `/api/v1/compasses` |
| `routers/forms_public.build_router` | a third mount, public prefix `k` |
| `access.get_form_for_user(…, mode)` | `'compass'`, so a kompas is not reachable through a forms URL |
| `services/limits._ENTITY_FILTERS` | `Form.mode == 'compass'`, its own ceiling |
| `useForms.makeApi(resource)` | a third `makeApi("compasses")` |
| the four organiser pages | registered a third time with `meta.resource` |

The two public routers currently branch on `is_quiz`. Three products
make that a mode-keyed lookup rather than a boolean, in the four places
it appears: the submit response model, whether `PUT /by-token` exists,
the ceiling kind, and the traffic surface name.

### 1.2 Naming

Dutch calls this a **kompas**. The code and the API call it a
**compass**, matching every other resource name in the tree
(`events`, `forms`, `datepolls`, `chores`, `quizzes`).

The word *Kieskompas* stays out of the product. Kieskompas B.V. is a
real company with a real product of that name, and shipping their name
on our pages invites a confusion nobody benefits from. The concept is
theirs and the name is theirs; "kompas" is the ordinary Dutch word and
says the same thing.

Public URL: `/k/{slug}`. `e`, `f`, `d`, `c` and `q` are taken, `c` by
chores, so the compass takes the letter its Dutch name starts with.
This is the first prefix that is not the English word's initial, which
is worth one line in `routers/spa.py` and no more.

### 1.3 The axes: a child table with exactly two rows

```
compass_axes
  id, tenant_id, created_at, updated_at        -- UUIDMixin + TimestampMixin + TenantMixin
  form_id      text not null  FK forms.id ON DELETE CASCADE, indexed
  axis         text not null  CHECK axis IN ('x', 'y')
  name         text not null                     -- "Economie"
  description  text null                         -- one line under the name
  low_name     text not null                     -- "Links", drawn left and bottom
  high_name    text not null                     -- "Rechts", drawn right and top
  UNIQUE (form_id, axis)
```

Two rows per kompas, always. That is a name and a line of description
per axis, and a name per side: six boxes on the create page, which is
what an organiser is asked to write and no more.

**A side gets a name and nothing else.** A description per side was
four more boxes for four more words, on top of an axis description
that already says what the whole line is about. Half-filled, they
leave a result screen that explains two sides out of four, which is
worse than a screen that explains none.

The alternative is twelve columns on `forms`, null on every survey and
every quiz, or one JSON blob. Twelve nullable columns on a table two
other products share is the shape rule #1 tells us to delete when we
find it, and a JSON blob gives up the CHECK and the NOT NULL that make
a half-configured kompas unrepresentable. Two rows with a unique key
cost one diff-apply, which we already write for questions and slots.

**Not bilingual.** `name` and `description` here are single-language,
in the form's own `locale`, exactly like `form_questions.prompt`. The
bilingual pair stops at the entity spine (`name_nl` / `name_en`,
`description_nl` / `description_en`) and has always stopped there;
`docs/design-bilingual-fields.md` is the rule and twenty-four columns
would be the reason to re-read it.

### 1.4 The poles: one column per shape

A **pole** is one of four tokens: `x_low`, `x_high`, `y_low`, `y_high`.
It names an axis and a direction along it, and it is the whole of what
a kompas adds to a question.

Which thing carries the pole depends on the kind, because the two kinds
put the choice in different places:

```
form_questions
  pole          text null    -- NEW: rating only. The pole a 5 means.
  option_poles  json null    -- NEW: single_choice only. One pole per option,
                             --      parallel to ``options``, same length.
```

**A rating question poles the statement.** "De overheid moet meer
huizen bouwen" is one claim on one axis, and the respondent says how
much they agree. A 5 is all the way toward the pole in `pole`, a 1 is
all the way toward the other end of the same axis, and a 3 is in the
middle. This is stemwijzer's shape exactly, one direction per question.

**A choice question poles each option.** "Waar moet het geld heen?"
with five answers is five different directions, and no single direction
belongs to the question. So each option carries its own pole, and the
options need not share an axis: three may sit on `x` and two on `y`.

`option_poles` is index-parallel to `options` rather than keyed by
option string, which is what `correct_choices` does. A key by string is
right for a *reference* into the options (the quiz key names some of
them) and wrong for an *attribute* of each of them: every option has
exactly one pole, and editing an option's text must not lose it.

Both columns are null on a survey and on a quiz, dropped on write in
`apply_questions` beside the five key columns, the same way `low_label`
is dropped on everything that is not a rating.

**Nothing changes about how an answer is stored.** A choice answer is
one entry in `form_responses.answer_choices`; a rating answer is
`form_responses.answer_int`. Both are what those kinds already write.
No new response column, no new answer shape, no new CSV cell type.

### 1.5 The migration

One revision:

- `compass_axes`, the table above.
- `form_questions.pole`, text, nullable.
- `form_questions.option_poles`, json, nullable.
- `ck_forms_mode` dropped and recreated with `'compass'` in it.

No data migration: pre-launch, and no row is a compass yet.

---

## Part 2: the numbers

`backend/services/compass.py`, the module that holds what is only true
when an answer has a direction. Everything else about a kompas lives in
`services/forms.py`, because everything else about a kompas is a
questionnaire.

### 2.1 What one answer is worth

Every answer, of either kind, produces one **contribution**: an axis,
and a value in [-1, 1].

```
rating, question pole p, answer v in 1..5
    axis  = p's axis
    value = (v - 3) / 2  *  (+1 if p is _high else -1)
            # 1 -> -1.0   2 -> -0.5   3 -> 0.0   4 -> +0.5   5 -> +1.0
            # against the pole, flipped when the pole is the low end

single_choice, chosen option with pole p
    axis  = p's axis
    value = +1 if p is _high else -1
```

The rating line is stemwijzer's `value * direction` with its answer
value map written out; the choice line is the same scale's two
endpoints. One scale, so a kompas that mixes the two kinds still means
something.

### 2.2 A position

```
for each answered question:
    axis, value = contribution(question, answer)
    bucket[axis].append(value)

x = mean(bucket["x"]) if bucket["x"] else 0.0
y = mean(bucket["y"]) if bucket["y"] else 0.0
```

Both coordinates land in [-1, 1] by construction. Rounded to three
decimals, which is finer than any pixel on the plot and coarse enough
that two identical answer sets produce two identical numbers.

**Why a mean and not a sum.** A kompas need not be balanced: the
organiser writes eight questions about one axis and three about the
other, and both axes still have to read on the same scale. A sum makes
the busier axis the longer one. A mean makes each axis "how far toward
this pole were your answers on this subject", which is the sentence the
result screen has to say anyway.

**A 3 is an answer; a skip is not.** A rating of 3 contributes 0.0 and
counts in the denominator, so it pulls the mean toward the centre. A
skipped question contributes nothing and is not counted at all. That
distinction is the reason a kompas needs no neutral *option*: the
neutral is the middle of the scale, on the kind that has one, and
saying nothing stays a different thing from saying "in the middle".

**An unanswered axis is 0.0, not null.** A respondent who skipped every
question touching `y` sits on the horizontal line, which is where
"nothing said" belongs, and the result screen says so in words rather
than leaving a dot unexplained. Part 4.4 refuses a kompas where an axis
is named by nothing at all, so this only happens through skipping.

A compass question keeps the `required` switch a questionnaire has and
a quiz does not. On a quiz, skipping is a free zero and had to be
refused; on a kompas, skipping is "I would rather not say", which the
mean already handles.

### 2.3 The functions

```python
contribution(question, row) -> tuple[str, float] | None
position_of(questions, rows) -> Position           # x, y, counted_x, counted_y
positions(db, form_id) -> dict[submission_id, Position]      # one query
validate_axes(axes) -> None                        # HTTPException(400)
validate_questions(questions, axes) -> None        # HTTPException(400)
```

`positions` is one `FormResponse` query grouped in Python, the same
shape as `quizzes.rows_by_submission`, because the organiser's page and
the respondent's plot both place every submission at once.

### 2.4 The plot, and what goes on it

A square scatter, domain [-1, 1] on both axes, four quadrants tinted,
the two axis lines through zero, and the four pole names at the four
edges. One dot per submission.

**Coincident dots cluster; they do not jitter.** Answer sets repeat,
especially on a short kompas, and dots will stack. Deterministic jitter
was the first idea and it is dishonest: it puts a dot where nobody is.
Instead, submissions at the same rounded coordinate render as one dot
whose radius grows with the count, and whose hover lists every name in
it. Your own submission's dot, or the cluster containing it, carries
the accent ring.

**Names come from the pseudonym and only from it.** A submission with
no name is a dot with no label; the hover says "anoniem" and the count
still includes it. This is the same identifier contract as every other
public surface in the app, and Part 5.1 says how the cover page makes
it honest.

**You see the room after you have answered, not before.** The
`/by-slug` payload the walk reads carries no points. They arrive with
the submit response and with `GET /by-token/{token}`. A kompas whose
map is readable without filling it in is a kompas people answer to fit
into.

---

## Part 3: what the respondent is asked

Two kinds: `rating` and `single_choice`.
`compass.COMPASS_KINDS = frozenset({"rating", "single_choice"})`,
refused at save with the reason, and never offered in the editor, which
is the pattern `QUIZ_KINDS` established.

A rating is the classic compass question: a statement, a five-point
scale, one direction. A choice is the question a five-point scale
cannot ask, where the answers are alternatives rather than degrees, and
where an answer may sit on either axis.

Not `multi_choice`: an answer that ticks three boxes pulls three ways
at once, and the honest handling (mean the picked poles, or count each)
is a rule that has to be explained on the page. Not `number`: a
headcount has no direction. Not the free-text kinds, for the same
reason a quiz refuses them.

The number of options per choice question is the organiser's: two,
five, seven. Nothing requires a question to cover both poles of its
axis, or to keep its options on one axis; a question may offer three
options on `x_low`, one on `y_high` and one on `x_high`, and the mean
handles it.

---

## Part 4: what the organiser writes

### 4.1 The edit page

`FormEditPage` grows a third variant. Above the question list, a new
**axes block**: two cards, one per axis, each with a name, a one-line
description, and the two poles with their names and descriptions. Six
name fields and six description fields, all on one page, none of them
behind a disclosure, because a kompas with an unnamed pole is a kompas
whose result screen cannot form a sentence.

Field order per card reads as the sentence it will produce:

```
As X
  [ Naam, bijvoorbeeld Economie                     ]
  [ Waar gaat deze as over?                         ]

  ←               [ Links                          ]
  →               [ Rechts                         ]
```

No field labels: a label and a placeholder above one box say the same
thing twice, and the placeholder is the one that carries the example
too. The arrow is the one thing a placeholder cannot say, which is
where a side lands on the map, and it carries the words for a screen
reader.

The two examples are the political compass's own axes
(`../stemwijzer/KOMPAS.md`): an economic one on x and a
social-cultural one on y, so the second card never repeats the first
card's words.

### 4.2 The question editor

`QuestionEditor` gets a third variant alongside `scored`. The kind
dropdown offers two kinds, and what appears under it depends on which:

**A rating** gets one pole select, under the scale labels, phrased as
the thing it decides:

```
Stelling   [ De overheid moet meer huizen bouwen     ]
Schaal     [ Helemaal oneens ]  …  [ Helemaal eens   ]
Een 5 betekent   [ Economie: Links            v ]
```

**A choice** gets one pole select per option, so the options list stops
being a list of strings and becomes a list of pairs:

```
[ Meer belasting op vermogen  ] [ Economie: Links   v ]
[ Lagere belastingen          ] [ Economie: Rechts  v ]
[ Strengere asielregels       ] [ Cultuur: Behoud   v ]
```

Every select's labels come from the axes block above, live, so renaming
an axis renames every select on the page. Before the axes are named,
the selects read `As X, kant 1` and so on, and saving is refused with
the message in 4.4.

`EditableList` renders strings; the choice variant is a list of pairs,
so it uses its own row markup and hands `options` and `option_poles`
back as two aligned arrays. That keeps the wire shape in 1.4 and keeps
`EditableList` doing the one thing it does.

### 4.3 Switching kind keeps what still applies

`QuestionEditor.patch` already clears fields that do not belong to the
new kind. The two pole fields join that rule: switching a rating to a
choice drops `pole` and gives every option an empty pole, and switching
back drops `option_poles`. A pole cannot survive the switch, because
the thing it was attached to did not.

### 4.4 What the server refuses

All of it at save time, none of it at submit time, because at submit
time the person who can fix it is not the person looking at the screen.
Each refusal names the question or the axis.

| Refused | Message (nl) |
|---|---|
| a kind that is not `rating` or `single_choice` | Vraag {n}: een kompas stelt alleen stellingen en meerkeuzevragen. |
| fewer than two options | Vraag {n}: een meerkeuzevraag heeft minstens twee antwoorden. |
| a rating with no pole | Vraag {n}: kies welke kant een 5 op deze schaal betekent. |
| an option with no pole | Vraag {n}: kies bij elk antwoord een kant van een as. |
| a pole outside the four | Vraag {n}: dit antwoord hoort bij een as die niet bestaat. |
| `option_poles` not the length of `options` | (unreachable from our editor, 400 with the same text) |
| an axis with no name | Geef as {X of Y} een naam. |
| a pole with no name | Geef beide kanten van as {naam} een naam. |
| an axis nothing ever names | Niemand kan bewegen op as {naam}: geen enkele vraag hoort erbij. |
| fewer or more than two axes | (unreachable from our editor, 400) |

The last one on the list is the rule Part 2.2 leans on. Any of the four
poles may be absent, which is the organiser's choice and sometimes the
honest one; an axis that nothing touches is not a choice, it is a
half-written kompas.

**The frontend refuses all of these first**, in the same words, before
the request goes out. This is lesson 7 and it is the one that took the
longest to learn on the quiz.

### 4.5 The details page

`FormDetailsPage`, third variant. Above the per-question list:

- **The plot**, every submission, no dot ringed, the same component the
  respondent sees.
- **Two axis bars**, one per axis: the group's mean marked on a
  [-1, 1] bar with the two pole names at the ends, and the spread
  (lowest and highest) as a lighter band behind it. Not a histogram:
  the coordinates are means of a handful of values and a bar chart of
  them is a picture of the question count, not of the room.

Per question, the existing aggregate gains its direction:

- **A choice question**'s option counts each carry the pole, in the
  organiser's own words. That is the difference between "34 people
  picked Rotterdam" and "34 mensen richting Rechts".
- **A rating question** keeps its five-bucket distribution and average,
  with the pole named under it and the average restated as a
  contribution: "gemiddeld 3,8 van 5, dat is 0,4 richting Links".

The CSV gains two columns, `x` and `y`, after `display_name`.

---

## Part 5: what a respondent sees

`/k/{slug}`, its own Vite entry (`public-compass.html`,
`src/public_compass/`), on the same budget as the other five.

### 5.1 The cover

Picture, title, description, the open-source disclosure, the name box,
and one sentence that the other five products do not need:

> Je naam komt op de kaart te staan die iedereen ziet die dit kompas
> invult. Laat het leeg als je liever anoniem meedoet.

That sentence is the privacy contract of this feature, it sits above
the box and not below it, and it is why the name is asked on the cover
rather than at the end. Leaving the box empty is a first-class choice:
an anonymous submission gets a dot like everybody else.

### 5.2 The walk

One question at a time, "vraag 3 van 10" as text, Back and Next, a
required question gating Next, one POST at the end. This is the quiz
walk exactly, and `public_shared/QuestionField.vue` already renders
both a `rating` and a `single_choice` question, so the walk is the
quiz's minus the score.

The poles are not in the page. `PublicQuestionOut` keeps its
list-the-fields-you-allow discipline, and neither `pole` nor
`option_poles` is on the list, so nobody answers a kompas by reading
which button moves them where. They arrive with the result, which is
the same seam and the same reason as the quiz key.

### 5.3 The result

Three blocks, in this order:

**1. The map.** Full width, square, your dot ringed, the rest of the
room around it, names on hover. First, because it is what the person
came for.

**2. Where you landed, per axis.** The axis name, its description, and
a sentence built from the organiser's own words:

> **Economie** Waar het geld vandaan komt.
> Je staat aan de kant van **Links**. `[ bar with your marker ]`
> *Links* ......................................... *Rechts*

Near zero the sentence reads "Je staat in het midden", and an axis you
answered nothing on reads "Je hebt geen vragen over deze as
beantwoord", because a dot on the centre line has two possible reasons
and the screen should say which one this is.

**3. Your answers, as they were asked.** One block per question, in the
question's own shape, with the direction named:

- **A rating** is redrawn as the scale it was, the five points in a row
  with your pick filled, the organiser's scale labels at the ends, and
  one line under it: "een 5 was Links, jij zei 4, dat is 0,5 richting
  Links".
- **A choice** is redrawn as its option list in the organiser's order,
  your pick marked with a filled dot, and each option's pole named on
  the right.

The mark grammar is the quiz result screen's, minus the key. The quiz's
`MarkedAnswer.vue` marks against a key and is not the same component;
what the two share is the row layout, which lives in
`public_shared/forms.css` already.

### 5.4 The link back

The token opens the result again, with the map redrawn against the
current room, which is free because nothing is stored.

Unlike a quiz, **the answers stay editable**: `PUT /by-token/{token}`,
the same as a questionnaire. Changing your answer after seeing the map
is changing your mind, not a second attempt with the answers in hand.
The result screen carries a "verander je antwoorden" button that
re-enters the walk with the answers filled in.

`POST /by-token/{token}/withdraw` works as it does everywhere:
withdrawing takes your dot off the map.

---

## Part 6: the sixth item, in full

None of it is interesting and all of it is required. Listed so it is
not discovered one file at a time, which is what Part 4 of the quiz
design was for and what it half-managed.

| Where | What |
|---|---|
| `models/forms.py` | `pole`, `option_poles`, `ck_forms_mode` gains `'compass'` |
| `models/compass.py` | `CompassAxis` |
| `services/compass.py` | contributions, positions, the two validators |
| `services/forms.py` | `apply_questions` drops/keeps the two pole fields; `apply_axes` beside it; `_validate_questions` calls the compass validators on `mode == 'compass'`; `question_aggregates` carries the poles |
| `schemas/forms.py` | `FormMode` gains a value; `CompassAxisIn/Out`, `CompassPoint`, `CompassAnswerResult`, `CompassResultOut`, `CompassSummary`; `pole` + `option_poles` on `FormQuestionIn/Out` and **not** on `PublicQuestionOut`; `axes` on `FormCreate`, `FormOut`, `PublicFormOut` |
| `routers/forms.py` | third mount, `/api/v1/compasses` |
| `routers/forms_public.py` | third mount, prefix `k`; `is_quiz` becomes a mode lookup in four places |
| `routers/start.py` | `POST /api/v1/start/compasses`, `_PREFIXES["compass"] = "k"` |
| `schemas/start.py` | `StartCompass` |
| `services/entities.py` | `create_form(…, mode="compass")` plus the axes |
| `services/limits.py` | a `compass` kind and its own ceiling |
| `services/slug.py` | `"compasses"` in `RESERVED_SLUGS` |
| `routers/spa.py` | `"k"` in `_PUBLIC_RESOLVERS`, `_serve_public_compass`, `/compasses/new` in `_APP_PAGE_META` |
| `routers/ads_txt.py` | `/compasses/new` in the sitemap |
| `models/traffic.py` | `create_compass`, `public_compass` in `SURFACES` |
| `alembic` | one revision, Part 1.5 |
| `frontend/vite.config.ts` | `k` in `PUBLIC_MINI_APP`, the new entry |
| `frontend/src/composables/useForms.ts` | `makeApi("compasses")`, and `useFormsApi` reads the resource rather than testing for one |
| `frontend/src/composables/useFormText.ts` | the copy helper, lesson 6 |
| `frontend/src/lib/form-urls.ts` | the public prefix per resource, so a list page stops handing out `/f/` links for a quiz |
| `frontend/src/router` | the four pages a third time, `meta.resource: "compasses"` |
| `frontend/src/components/QuestionEditor.vue` | the pole variants, 4.2 |
| `frontend/src/components/CompassAxesEditor.vue` | the axes block, 4.1 |
| `frontend/src/components/CompassPlot.vue` | the scatter, shared by the details page and the mini-app |
| `frontend/src/public_compass/` | cover, walk, result |
| `frontend/src/locales/{nl,en}.json` | a complete `compasses.*` block, and the `quizzes.archived.*` keys that are missing today |
| three landing pages | the sixth tile, `PersonalIndexPage` + `HomePage` + `AppHeader` |
| `docs/architecture.md` | the sixth item |

---

## Part 7: what this deliberately does not do

- **No archetypes.** The organiser cannot place parties, positions or
  named reference points on the map. Asked for, and out: it is a second
  editor, a second set of coordinates, and a matching rule
  (stemwijzer's `computePartyScores`) that is a product decision of its
  own. The data model does not block it: an archetype is a row with two
  coordinates and a name.
- **No pole-less answer.** Every option carries a pole and every rating
  carries one. The neutral a kompas needs is a 3 on a scale, not an
  option that means nothing, and "no opinion at all" is a skipped
  question (2.2).
- **No per-answer weight.** Every answer moves you as far as its own
  value says. Stemwijzer weights by how important the respondent said a
  question was; that is a second question per question, and it changes
  the walk.
- **No more than two axes.** Two is what a scatter can show. Three is a
  different picture and a different product.
- **No "who am I closest to".** A ranked list of the people nearest you
  on a map, by name, is a sociogram of a political meeting. The map
  shows where everyone is; it does not compute anybody's neighbours.
- **No clusters, dendrograms or heatmaps.** Stemwijzer has all three
  (`frontend/js/components/`). They answer questions an organiser of an
  evening does not have.
- **No axis auto-mapping.** `KOMPAS.md`'s correlation method derives an
  axis from how known parties voted. We have no parties, and the
  organiser writing the question knows what it is about.
- **No written SEO page yet.** `services/content.py` has five and this
  will want a sixth ("een kompas maken zonder account"). After it
  works, not before.

---

## Order of work

Each step leaves the tree working and the suite green.

1. **The copy helper and its enumerating test**, on the two products
   that exist. No compass yet, and it repays itself on the quiz
   immediately (lesson 6).
2. **The migration and the model**: `compass_axes`, the two pole
   columns, the widened CHECK. Still no compass: the two products
   behave exactly as before, now with the seam in place.
3. **`services/compass.py`**, contributions, positions and validators,
   with the arithmetic in Part 2 under test before anything renders it.
4. **The backend surface**: schemas, `apply_axes`, the third mounts,
   start, limits, slug, spa, traffic. `make openapi`.
5. **The organiser pages**: the axes editor, the question editor's two
   pole variants, the third route registration, the full `compasses.*`
   block.
6. **`CompassPlot.vue`**, once, tested against a fixed domain and a
   coincident-dot case, then used by the details page.
7. **`public_compass`**: cover, walk, result, using the same plot.
8. **The sixth tile**, on all three landing pages, once there is
   something behind it.
