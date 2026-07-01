# 12 — Volunteer actions: pass / cover / swap / availability + confirmed-vs-outlook UI

**Layer:** backend + frontend · **Depends on:** 11 (projection, pinned window) ·
**Design refs:** §7 (pass/cover/swap/availability; what a volunteer sees), §9 (public API),
§14.5.

## Goal

Give volunteers the full set of self-service actions on their **confirmed** shifts, and make
the personal page honestly separate the reliable window from the tentative outlook. Replaces
the single `handoff` action with the richer, ledger-aware set.

## Backend

New / reworked public endpoints (`routers/chores_public.py`, all edit-token authed, all
`@limiter.limit`):

- `POST .../shifts/{shift_id}/pass` — the pinned assignee opts out. Reassign the occurrence
  via WRH excluding them; if nobody eligible → `open`. Writes `deferred` for the passer and
  `assigned`/`claimed`/`covered` as appropriate for the taker. (Replaces `handoff`; delete
  `handoff` and `reassign_shift`'s old shape.)
- `POST .../shifts/{shift_id}/cover` — a volunteer takes **another's** confirmed shift.
  One-way: they become assignee. Writes `covered` (credit taker +, covered −). Guard: shift
  must be confirmed and held by someone else.
- `POST .../shifts/{shift_id}/claim` — take an `open` shift. Writes `claimed`. (Exists;
  keep, ensure it emits the event.)
- `POST .../swap` `{mine_shift_id, theirs_shift_id}` — optional two-way trade of two
  confirmed occurrences; both become pinned overrides to the other person; ledger-neutral.
  Guard: requester holds `mine`, target holds `theirs`, both in the window.
- `PUT .../availability` `{ranges: [{start, end}]}` — store per-volunteer away ranges.
  New `VolunteerAvailability` table (or JSON column on `Volunteer` — prefer a small table:
  `volunteer_id` FK CASCADE, `start_date`, `end_date`). Feeds the eligible/available set in
  the projection + pin step (task 10's `available` set becomes `enrolled − unavailable`).

`make openapi` + types after all of the above.

## Frontend (`PublicChore.vue`, personal mode)

Two clearly separated tiers (§7):
- **Confirmed** — pinned window. Each shift: **Mark done**, **Can't make it (pass)**, and
  where applicable **Swap**. Others' confirmed shifts surface a **Cover** affordance
  ("someone needs cover" / voluntary take-over list).
- **Outlook** — projected beyond the horizon, greyed/labelled "likely, may change", **not**
  actionable, no reminders.
- **Availability** editor: add/remove away ranges (a simple date-range list), with copy that
  it affects future turns, not confirmed ones already pinned.

nl + en, locked-step.

## Tests

- **`tests/test_chores_public.py`** extended: pass reassigns + emits `deferred`; cover
  transfers + emits `covered` with correct credit signs; swap trades two shifts
  ledger-neutral; claim emits `claimed`; availability excludes a volunteer from future pins
  (assert a pinned assignment avoids an away volunteer after the next tick).
- Guard tests: cannot cover your own shift; cannot swap shifts you don't hold; cannot act on
  an outlook (unpinned) occurrence.
- Leak guard still green (no email/ciphertext/token in any personal-page payload).

## Acceptance

`uv run pytest --no-cov` green; `make openapi` no diff; `uv run ruff check backend tests`
clean; `npm run test` + `npx vue-tsc --noEmit` green; migration idempotent.

## Out of scope

Automatic membership add/remove reflow (task 13) — this task is about *voluntary* actions.
Accountability display (task 14).
