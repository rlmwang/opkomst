# 14 — Accountability: regular turns vs picked-up-for-others

**Layer:** backend + frontend · **Depends on:** 09 (accountability stats + `ShiftEvent`),
12 (`covered`), 13 (`inherited`) · **Design refs:** §7 ("Event log, favour ledger, and
accountability"), §10 (details page).

## Goal

Extend the per-volunteer accountability display (task 09) so it distinguishes **regular
turns** (shifts WRH assigned to them, their fair share) from **shifts picked up for others**
(help beyond their share), the latter **including slack absorbed when another volunteer was
removed**. A volunteer who quietly covers should read as more reliable, not just "did N".

## The split (provenance from `ShiftEvent.kind`)

No new columns: the split is a tally of the acquisition `kind` per volunteer (§7 table):

- **Regular turns** = count of `assigned`.
- **Picked up for others** = count of `claimed` + `covered` + `inherited`.
- **Outcomes** = `completed` / `deferred` (passed) / `missed` (as task 09).

`inherited` is the removal-pickup provenance added in task 13; `covered` the voluntary
take-over from task 12. If either is not yet present in the log, its count is simply 0, so
this task degrades gracefully if landed before those.

## Deliverables

1. **Aggregation** — extend the single grouped `ShiftEvent` query in `services/chores.py`
   to bucket the pickup kinds separately from `assigned`. Fold into `VolunteerSummaryOut`:
   add `regular_turns`, `picked_up` (sum of the three pickup kinds), and keep the existing
   `completed`/`deferred`/`missed`. Optionally expose the pickup breakdown
   (`claimed`/`covered`/`inherited`) too, or keep it summed — your call, but the **details
   page must at least show regular vs picked-up**.
2. **`make openapi`** + frontend types.
3. **Details page** — `ChoresDetailsPage.vue` volunteer card: alongside the done/handed-
   off/missed breakdown, show **regular turns** and **picked up for others** (a chip or
   small two-column figure). Copy should read as recognition of extra help, not clutter.
   nl + en, locked-step. Still **no email/ciphertext/token** in the projection.

## Tests

- **`tests/test_shift_events.py`** extended: aggregation returns correct `regular_turns` vs
  `picked_up` for a volunteer with a mix of `assigned` + `claimed` + `covered` + `inherited`
  events; an inherited (removal) pickup counts under `picked_up`, not `regular_turns`.
- Leak guard: the new count fields present, still no email/ciphertext/token.

## Acceptance

`uv run pytest --no-cov` green; `make openapi` no diff; `uv run ruff check backend tests`
clean; `npm run test` + `npx vue-tsc --noEmit` green.

## Out of scope

Per-chore breakdowns, streaks/leaderboards, exporting; enforcement or notifications
(display-only), consistent with task 09.
