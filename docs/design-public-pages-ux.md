# The public pages

Six products, one public page grammar. A visitor who has seen one has
seen them all, and the shared parts live in `frontend/src/public_shared/`
rather than in six copies.

## The skeleton

Every public page is: a header with the brand and a language toggle, a
top card with the title, the image and the description, the
open-source disclosure, then one card with the form in it.

The pseudonym field comes first, above the questions, because it is the
one thing the page asks about the person rather than about the thing.
It is optional unless the organiser said otherwise.

After a submit the page collapses to a single confirmation card:
a thank-you, the secret link, a copy button and the warning that nobody
can re-send it (`docs/design-edit-link.md`). The quiz and the kompas
show their result instead, with the same link card at the end.

Nothing on a public page loads a third-party script.

## The organiser form's fold

Every edit page ends the same way, on all six products:

* **Above the fold**, what the thing *is*: its name, its words, its
  picture, its chapter, its when and where, its questions or chores or
  dates. The event's "show on the chapter agenda" switch is up here
  too, because it is about where the event appears rather than about
  how the form behaves.
* **Inside `details.advanced`**, every switch that changes behaviour,
  plus the fields a switch reveals. It starts closed, always: a form
  that decides for itself when to unfold is a form whose length changes
  for reasons nobody asked for.
* **Below it**, the page language.

The `.advanced` rules live in `src/assets/forms.css` with the rest of
the shared form chrome, so no page carries its own copy.
