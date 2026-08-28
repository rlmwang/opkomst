# Quizzes

A questionnaire with an answer key. Same tables, same editor, same
public page; what differs is that an answer can be right.

## One table, three products

`Form.mode` is `survey`, `quiz` or `compass`. A quiz is not a second set
of tables, because a quiz question is a form question with a key and a
number of points on it.

Every read of the `forms` table names the mode it means. That rule has
one implementation, `services/forms.query`, and a test greps the tree
for anyone reading the table anywhere else. Without it a quiz shows up
in the questionnaire list.

## The key, per kind

| Kind | What "right" means |
|---|---|
| Multiple choice | the correct option, or several |
| Number | an exact value, or a value within a margin |
| Rating | the correct point on the scale |
| Text | nothing: a quiz cannot mark an open answer |

Points are per question, so one question can be worth more than another.
Change a key or the points afterwards and every score is recomputed from
the answers already on file.

## What a quiz does that a questionnaire does not

* Questions come one at a time, so the next one is not readable before
  you have answered this one.
* The result screen shows the score, and optionally which answers were
  right. An organiser running the same quiz twice in one evening turns
  that off.
* There is no edit link back into the answers. Seeing the score and then
  changing your answers is the definition of cheating, so a quiz has no
  edit path at all.

## Where it lives

```
backend/services/quizzes.py    grading and key validation
backend/services/forms.py      everything a quiz shares with a form
frontend/src/public_quiz/      the player's side
```
