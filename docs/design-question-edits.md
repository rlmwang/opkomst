# Editing a question after people have answered it

Status: built. `tests/test_question_edits.py` is what it proves.

An organiser can change a form, a quiz, a kompas or an event at any time,
including after answers are in. Some of those edits leave the stored
answers meaningful and some do not. Today the difference is not modelled,
so the damaging edits go through silently.

Answers here are anonymous and one-shot. Nobody can be asked again, so a
lost answer is lost for good.

## What happens today

Measured against the real endpoints with data created for the purpose:
one `multiple_choice` question with three answers (`Wekelijks` x2,
`Maandelijks` x1). These are behaviours of the code, not observations of
how organisers actually edit forms, which nobody can have yet.

| Organiser action | Survey / quiz | Kompas |
| --- | --- | --- |
| Add an option | safe | safe |
| Reorder options (editor moves the directions with them) | safe | safe |
| **Rename an option** | counts show `Elke week: 0`, CSV still shows `Wekelijks`, `response_count` stays 3 while the counts sum to 1 | the answer stops counting and the dot moves to 0.0 |
| **Delete an answered option** | same orphaning | same |
| **Change the question kind** | `counts=None`, `response_count=0`, CSV empty, rows still on disk | same |
| **Retype the question** (editor drops the id) | answers deleted by cascade | same |
| Change which direction an option means | n/a | every dot moves, intended |
| Change a quiz's correct answer | rescored, intended | n/a |

The kompas rename is the worst of these. A dot at 0.0 is drawn dead
centre, so somebody who answered "meer collectief" is displayed as a
moderate. Nothing tells the organiser this happened.

There is a fourth state hiding in that table, worse than either keeping
or deleting: after a kind change the answers are on disk but no surface
can read them. They are neither data nor gone.

### Events have the same problem

`Signup.source_choice` and `Signup.help_choices` store copies of text from
`Event.source_options` and `Event.help_options`. Renaming an option there
fails too, and the two tallies fail differently, because one is seeded
from the option list and the other is grouped from the stored values.

| Tally | Built from | Effect of a rename |
| --- | --- | --- |
| form choice counts | the question's options | renamed option reads 0, answers vanish |
| event `by_help` | the event's help options | same, answers vanish |
| event `by_source` | the stored values themselves | the old name lingers as a bucket of its own |

## Why it breaks

Three identity rules, none of them agreeing.

1. **An answer points at an option by its text.** `answer_choices`,
   `help_choices` and `source_choice` all store the option string. Rename
   the option and the link is gone.
2. **An option points at its direction by position.**
   `compass.contribution` does `options.index(text)` and then
   `poles[index]`. The answer is matched by text and its meaning by
   position.
3. **A question is identified by its row id.** The id says the row still
   exists. It does not say the row still means what it meant, so a kind
   change keeps the id while invalidating every answer under it.

Question ids are otherwise sound: `apply_questions` mints a fresh uuid
for inserts and ignores a client-supplied one, and scopes lookups to the
form, so no id can collide across forms.

Related, worth fixing in the same pass: `apply_questions` pairs options
with directions using `zip(..., strict=False)`, which silently truncates
when the two lists disagree in length.

### The rule this suggests

**JSON is fine for a value nothing points at. It is wrong for a value
something else stores a copy of.**

By that test `cycle_slots` stays JSON: it is configuration and nothing
references it. The option lists do not, because answers reference them.

## Decisions

### 1. A kind change is a delete and an insert

If the submitted kind differs from the stored kind, do not update the row.
Fall through to the insert branch. The old row is then absent from
`seen_ids` and the existing delete pass removes it, taking its answers
with it.

A rating question is not the multiple-choice question people answered, so
the answers genuinely do not carry over. It also makes the two paths
agree: retyping a question and changing its kind mean the same thing to an
organiser, and now do the same thing. And it removes the
unreadable-but-present state entirely.

Verified the cascade behaves: with two questions and three submissions,
deleting one question took responses from 6 to 3, left the other
question's answers alone, and left all three submissions and both question
rows intact.

Two lines in the update branch of `apply_questions`.

### 2. One gate for every destructive edit

Three edits destroy answers: removing a question, changing a question's
kind (decision 1), and removing an answered option. All three go through
one check.

The update path already computes this diff. It counts the answers a save
would destroy and refuses unless the request carries an explicit
confirmation, so the editor can say:

> This removes 12 answers to "Hoe vaak kom je?". Save anyway?

Without this, decision 1 ships silent deletion, which is worse than the
orphaning it replaces.

### 3. Options become tables

Five new tables, replacing five JSON columns, plus one text column
that becomes a foreign key.

```
form_question_options
    id, question_id -> form_questions, ordinal, label, pole, is_correct

form_response_choices
    id, response_id -> form_responses, option_id -> form_question_options

event_source_options
    id, event_id -> events, ordinal, label

event_help_options
    id, event_id -> events, ordinal, label

signup_help_choices
    id, signup_id -> signups, help_option_id -> event_help_options
```

and `Signup.source_choice` becomes `source_option_id`, a foreign key.

Replaced: `FormQuestion.options`, `FormQuestion.option_poles`,
`FormQuestion.correct_choices`, `FormResponse.answer_choices`,
`Event.source_options`, `Event.help_options`, `Signup.help_choices`,
`Signup.source_choice`.

`pole` and `is_correct` move onto the option row, which is what removes
identity rule 2. A direction is a property of an option, not of its
position in a list, and the same is true of being the right answer.

What this buys beyond ids alone:

- A foreign key makes orphaning impossible rather than merely handled.
  Renaming is a label update and every answer still points at the same
  row.
- Deleting an option becomes a constraint decision instead of a silent
  drop: `RESTRICT` refuses while answers exist, and decision 2's
  confirmation is what turns it into a `CASCADE`.
- Counting is a plain join and `GROUP BY`. This deletes the
  `json_array_elements_text` unnest, the `json_typeof(...) = 'array'`
  guard and the JSON-null trap from the aggregate query in
  `services/forms`.

Every new table carries `tenant_id` through `TenantMixin`, as all tables
here do. Archive twins need no work: they are generated from the
foreign-key graph, so the new tables are mirrored automatically
(`models/archive.py`).

**Do this before launch.** There is no production data (see CLAUDE.md),
so there is nothing to migrate: it is a schema edit against a database
nobody has used. After launch it becomes a migration that has to map
stored answer text onto option rows, and every option an organiser has
renamed by then is an answer that mapping cannot place.

**This changes the API contract.** `options` stops being `list[str]` and
becomes rows with ids, on the organiser editor, all three public
renderers and the event form. That is roughly 200 references across 20
frontend files, currently existing in both a Vue and a Svelte version.
Decision 3's backend and frontend halves have to land together.

### 4. The editor must preserve ids

Ids only work if the editor keeps them. If reordering questions or options
means retyping them, the ids die and the cascade deletes real answers,
invisibly, with no backend defence possible.

So the editor treats questions and options as rows with identity: drag to
reorder, edit the label in place. Never a free-text list rewritten whole.

This is the only decision here that cannot be enforced in the backend, and
the one that silently deletes data if ignored.

## Rejected

**Match options by position.** Rename becomes free, but reordering
silently remaps every stored answer and inserting an option mid-list
corrupts everything after it. Worse than today for the common case.

**Ids inside the JSON.** `options` becomes `[{id, label}]` and answers
store ids. Fixes rename and reorder without new tables. Rejected because
nothing enforces the reference: an answer can still name an option that no
longer exists, so every reader keeps a defensive branch, and the json
unnest, the `json_typeof` guard and the JSON-null trap all stay. It is
most of the work of decision 3 for none of the guarantee.

**Version questions.** An invalidating edit retires the old row and
inserts a new one, keeping old answers readable against the old
definition. Never loses data, and it is the textbook answer. Rejected on
cost: the summary must render retired questions that still hold answers,
the CSV export grows a column per version, and the editor must show them
read-only. A permanent tax on three surfaces. With decision 3 in place the
invalidating category shrinks to the kind change alone, which decision 1
handles in two lines.

**Refuse the edit while answers exist.** Simple, but an organiser who
typed "Wekelijsk" could never fix it on a live form. Bad answer for a tool
volunteers use.

**Migrate renamed options automatically.** Detect a rename and rewrite the
stored answers. Cheap, but ambiguous when two options are renamed at once,
or a rename coincides with a reorder. Guessing wrong rewrites what people
said, which is worse than the current failure. Decision 2 resolves the same
ambiguity by asking the organiser.

## Order of work

1. **Decisions 1 and 2.** Backend only, no schema change, no API change.
   Shipping 1 without 2 means shipping silent deletion, so they go
   together.
2. **Decision 3.** Schema, then the readers, then the API shape, then the
   frontend. Backend and frontend land together because the contract
   changes. Before launch, and before the Svelte rewrite settles, since
   both versions of every affected component would otherwise need doing
   twice.
3. **Decision 4**, in the same pass as 3's frontend half.

Decisions 1 and 2 do not fix the option rename. That is decision 3's job,
and until it lands a rename still orphans answers silently.
