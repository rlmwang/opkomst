# The edit link

Somebody who fills in a public page gets a secret link back to what they
sent. It is the only way back, and it is shown once, on the
confirmation screen, with a copy button.

There are no accounts on the public side, so the link is the identity.
The token is stored hashed; the plaintext exists in that URL and
nowhere else. Nobody can re-send it, and the page says so.

What the link opens depends on the product. A sign-up, a questionnaire
answer, a date-poll answer and a kompas result open for editing. A quiz
result opens read-only, because seeing the score and then changing the
answers is the definition of cheating. A roster's link opens the
volunteer's own page, which is the product rather than a submission.

Two switches the organiser owns:

* **`answers_editable`** decides whether the link may still change
  anything. Off when the headcount or the date has to stop moving. It
  never closes the link itself, and it never blocks withdrawing:
  taking your answers back is a different right.
* **`name_required`** decides whether a public write is refused without
  a name. Off by default on all six products: a name real or not is
  what the contract offers, so an empty box is an answer.

An organiser can mint a fresh link for somebody who lost theirs. That
is recorded on the submission and shown on the respondent's page, so a
link that was handed over does not look like a link that was never
touched.
