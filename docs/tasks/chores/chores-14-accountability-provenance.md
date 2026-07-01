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

1. **Aggregation as a pure fold** (design §7 "The pure core") —
   `summarize_accountability(events: Iterable[tuple[kind, volunteer_id]]) ->
   dict[str, Counts]` bucketing `regular_turns` (`assigned`), `picked_up`
   (`claimed`+`covered`+`inherited`), and `completed`/`deferred`/`missed`. It folds the
   **same** `(kind, volunteer_id)` event stream as `net_credit` (task 10), so ledger and
   stats provably read one source — assert that shared-input consistency in a test. A thin
   impure wrapper queries the rows and hands them to the fold; the result folds into
   `VolunteerSummaryOut` (`regular_turns`, `picked_up`, plus the existing outcomes).
   Optionally expose the pickup breakdown too, but the **details page must at least show
   regular vs picked-up**.
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
