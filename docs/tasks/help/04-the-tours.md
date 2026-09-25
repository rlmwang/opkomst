# 04: The six tours, their copy, the menu group, the door link

Design: `docs/design-tour.md` chapters 4, 9 (the menu and the door)
and 11. When this lands, every tour but the welcome can be started
from the app.

## The tours

`frontend/src/tours/tours.ts`: the six tours as data, exactly the
step tables in design chapter 4, plus `frontend/src/tours/index.ts`
mapping a route family to the tour the menu offers:

| route family | tour |
|---|---|
| `/{resource}` and `/{resource}/archived` | lijst |
| `/{resource}/:id` | details |
| `/{resource}/new`, `/{resource}/:id/edit` | formulier |
| `/users`, `/chapters`, `/settings` | beheer |
| `/` signed in | welkom (from the card only, task 05) |
| `/` signed out | inloggen (from the door link only) |

The product is read from the route's resource segment and passed to
`start(id, product)` so the copy lookup can prefer product keys.

## Copy

All strings under `tour.` in `nl.json` and `en.json`, keyed
`tour.{id}.{product}.{n}.title` and `.body` with the generic fallback
`tour.{id}.{n}.*`, resolved through `formText()`'s product-then-generic
rule. Titles are the question the step answers, at most six words.
Bodies are at most two sentences; the tables in design chapter 4 are
the Dutch. The sign-in tour's step 4 has an organisation variant
under `tour.inloggen.4.body.organisation`, chosen by the same
`isPersonalApp()` switch the door uses.

Write the Dutch first and natively; `docs/style-nederlands.md`
applies. The parity test from task 01 keeps English in step.

## The menu group

`AppHeader.svelte`: a fourth group in the nav menu, after the admin
items and before the sign-out rule: Rondleiding, which calls
`tour.start()` with the tour for the current route family, and
Handleiding, which task 07 wires to the manual's chapter (until then
the item is not rendered; do not ship a dead item). Rondleiding is not
rendered when `auth.needsChapters`, because every list step would be
dropped. Nothing is added to the header bar.

## The door link

`components/OrganiserDoor.svelte`: one text link under the form,
"Hoe werkt inloggen?", `auth.howToSignIn` in both locales, which
starts the sign-in tour. It is the one tour the engine allows without
a session; the store's `start` accepts it signed out because all its
steps live on the landing page.

## Tests

- `tours.test.ts`: every anchor a tour names is in the `AnchorName`
  union (a compile error already, but the test walks the data so a
  renamed anchor fails with the tour's name in the message); no tour
  has more than five steps; no step body in either locale has more
  than two sentences (split on `. `, `? `, `! `); every step has both
  title and body in both locales, for the generic key at least.
- `app-header` test: the menu shows Rondleiding for a signed-in
  approved user on a list route and not when `needsChapters`.
- The parity test from task 01 covers the keys.

**Done when:** on a list, details, form or admin page, the menu starts
the right tour and it runs to Klaar with the page's own controls; the
door link runs the sign-in tour to step 4 against the dev mail
backend; every string is in both locales.
