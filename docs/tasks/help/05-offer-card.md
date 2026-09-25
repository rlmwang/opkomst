# 05: The offer card, its column and endpoint, the two e2e tests

Design: `docs/design-tour.md` chapter 9 (offered once, the record)
and chapter 13 (the two end-to-end tests). When this lands the tour
is complete.

## Backend

- `models/users.py`: `tour_offered_at: Mapped[datetime | None]`,
  nullable, no index. One Alembic revision.
- `schemas/auth.py::UserOut`: `tour_offered: bool`, filled in
  `routers/auth.py::_user_out` from the column, beside
  `participant_mail`.
- `POST /api/v1/auth/tour-offer`, in `routers/auth.py`, authenticated,
  `@limiter.limit(Limits.ORG_WRITE)`, no body: sets the timestamp to
  now if null and returns the `UserOut`. Idempotent. Logs the route
  name and outcome, nothing else.
- `make openapi`.

## Frontend

- `stores/auth.svelte.ts`: `tourOffered` getter beside
  `participantMail`.
- `composables/useTourOffer.svelte.ts`: one mutation calling the
  endpoint with an optimistic patch of the session payload and its
  undo, the way the other mutations are shaped.
- `pages/HomePage.svelte`, signed-in face: when `auth.isApproved &&
  !auth.tourOffered`, an `AppCard` above `TileGrid` in the same
  column: title `home.tourOfferTitle` ("Nieuw hier?"), one line
  `home.tourOfferBody` ("In vijf stappen maak je je eerste
  evenement."), buttons `home.tourOfferStart` ("Start de rondleiding")
  and `home.tourOfferDecline` ("Nee, bedankt"). Either button calls
  the mutation; Start also calls `tour.start("welkom", "event")`. The
  card never returns.
- The Handleiding menu item stays for task 07.

## End-to-end tests

Both in `frontend/e2e/`, both signing in through
`/api/v1/auth/dev-issue-token` like the others. The seed leaves
`tour_offered_at` null for the seeded organiser, and `cleanup.ts`
resets it, so the welcome test is repeatable.

- `tour-welcome.spec.ts`: sign in, land on `/`, see the card, press
  Start, then at each step do what the body says: click the events
  tile, click Nieuw evenement, type a name and pick a date and press
  Opslaan, press Volgende at the share link, press Klaar at the menu.
  Assert the URL is a details page and the overlay is gone. Reload
  `/` and assert the card is gone. This is also the test that catches
  a dropped step in a tour whose count is declared: assert the counter
  reads "5 van 5" on the last step.
- `tour-signin.spec.ts`: signed out at `/`, click "Hoe werkt
  inloggen?", see "1 van 4", press Volgende, type the seeded
  organiser's address and press Stuur link, assert step 3 lights the
  sent paragraph, press Volgende twice, overlay gone.

## Tests, unit

- `tests/test_auth.py`: the endpoint sets the timestamp once, a second
  call leaves it, the payload carries the boolean, an unauthenticated
  call is 401.
- `tests/test_rate_limits_audit.py` passes as is.
- `stores.test.ts`: the getter reads the payload.

**Done when:** a fresh account sees the card once and never again on
any device; the two e2e specs pass in the pre-push run; `openapi.json`
and `schema.ts` are regenerated.
