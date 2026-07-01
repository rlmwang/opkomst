# 11 — Projection model, commit horizon, and roster lifecycle

**Layer:** backend (+ small frontend read changes) · **Depends on:** 10 (deterministic
assignment) · **Design refs:** §4 (`commit_horizon_days`, `activated_at`), §5 (sparse
overlay), §7 (three zones, the tick, bootstrap/activation), §14.3/§14.6.

## Goal

Stop eagerly materialising a fixed 28-day horizon. Treat occurrences as a **deterministic
projection** of the pattern (task 10) and keep `Shift` rows only as a **sparse overlay**
materialised inside a configurable **commit horizon**. Add the `forming → running` lifecycle
gate so a roster promises nothing until the organiser starts it. This closes the
edit-divergence bug at the root and gives unbounded, honest lookahead.

## Model changes

`Roster` gains (one Alembic migration, idempotent):
- `commit_horizon_days : int` (no code default; through `RosterCreate`, e.g. UI default 21).
  Validated `>= reminder_days_before`.
- `activated_at : datetime | None` — `NULL` = forming, set = running. One-way.

No `Shift` schema change: rows already key on `(chore_id, on_date, slot_index)`. The change
is *when* they exist — only for occurrences inside the horizon or acted upon.

## The tick (rewrite `chore_tick.run_tick`)

Per **running** (non-archived, `activated_at` set) roster:

1. **Pin the incoming edge.** For each occurrence in `[today, today + commit_horizon_days]`
   (capped by `ends_on`, floored by `starts_on`) with no `Shift` row: compute its WRH
   assignment (task 10, current ledger) and insert a pinned row (`scheduled`, or `open` if
   nobody eligible). Additive + idempotent; never touches an existing row. Optionally apply
   a deterministic same-day de-collision pass here (window-only).
2. **Prune stale pins (window-only).** Delete pinned rows inside the window that are
   **not yet reminded and not yet acted on** (`status='scheduled'`, `reminder_sent_at IS
   NULL`, no `completed`/`deferred` event) whose occurrence no longer projects (date no
   longer occurs / slot dropped / before `starts_on`). Never touch reminded/acted rows;
   never touch `on_date < today`.
3. **Reconcile the past.** `on_date < today` still `scheduled` → `missed` (+ `missed`
   event), as today.

A `forming` roster is skipped entirely (nothing pinned). Delete the old `_extend` full-
horizon loop, the `HORIZON_DAYS = 28` constant, and the "reopen SET-NULL scheduled" block
(membership handling moves to task 13).

## The pure core (extract these; see design §7 "The pure core")

This task introduces the pure-function spine the tick and reads both run on. All are I/O-free
and speak **value objects**, never ORM rows:

- **Value objects** (`dataclass`/`NamedTuple`): `Occurrence(chore_id, on_date, slot_index)`,
  `ProjectedAssignment(occurrence, volunteer_id | None)`, `PinnedShift(key, status,
  reminded: bool, acted: bool, assignee)`, `Diff(insert, prune, keep)`.
- **`occurrences_between(chores, period_weeks, starts_on, ends_on, start, end) ->
  list[Occurrence]`** — the single "what occurrences exist" oracle, over `occurs_on`. Used by
  *both* the tick's pin step and the read-side outlook, so confirmed and outlook are provably
  the same enumeration.
- **`project(occurrences, resolve_eligible, weights) -> list[ProjectedAssignment]`** — maps
  each occurrence through `assign_occurrence` (task 10). Pure given resolved eligibles +
  weights.
- **`reconcile(existing_pins, projected, *, today) -> Diff`** — the edit-correctness
  function. Rules: un-acted stale pin (not in `projected`, `status='scheduled'`,
  `reminder_sent_at IS NULL`, no act event) → **prune**; reminded or acted → **keep**;
  `on_date < today` → **never touch**; projected-but-unpinned in window → **insert**. This is
  where the whole divergence question is decided, so it is tested exhaustively with plain
  value objects and no DB.

The impure `chore_tick`/`services` layer only: reads rows → value objects, resolves
`enrolled ∩ available` + ledger→weights, calls the above, and **applies the `Diff`**.

While establishing the pure core, also extract **`reminder_due(shift, roster, *, now) ->
bool`** from the existing reminder worker (task 08): the fiddly civil-time / days-before /
opted-in decision becomes a pure predicate, the worker keeps only the query + send. Small,
and it completes the "every decision is a pure function" story.

## Reads become projection-aware

- `services/chores.py::schedule` returns two tiers: **confirmed** (pinned rows in the
  window) and **outlook** (`occurrences_between` + `project` beyond the window, computed on
  demand, date-bounded — no infinite lists; cap at a sane render window like 90 days with the
  cap stated in the response).
- `personal_page` likewise: "your confirmed turns" (pinned, actionable) vs "outlook"
  (projected, tentative, non-actionable).

## Activation endpoints (organiser)

- `POST /chores/{id}/activate` — forming → running (sets `activated_at`); 409 if already
  running. `@limiter.limit`.
- `POST /chores/{id}/rebalance` — re-pin the current window from the fresh projection
  (drops un-acted pins, re-pins). Confirmation-gated in the UI; changes confirmed shifts.
  `@limiter.limit`. (Full "fold pending in early" semantics finished in task 12/13; here it
  is "re-derive the window now".)

## Frontend (minimal here; full UI in 12)

- `make openapi` + types.
- `ChoresEditPage`: `commit_horizon_days` control (validated `>= reminder_days_before`).
- Schedule view splits confirmed vs outlook (labels only; rich UI in 12).

## Tests

- **`tests/test_chore_tick.py`** (rewrite): pinning idempotent + additive; window-only
  prune drops un-acted stale pins, keeps reminded/acted, never touches past; forming roster
  pins nothing; editing `starts_on`/`period_weeks` leaves valid pins' assignees unchanged
  (uses task-10 date-keying) and prunes only orphaned un-acted pins.
- **`tests/test_chore_projection.py`** (new): `occurrences_between` enumerates exactly the
  pattern's occurrences in a window (pure, no DB); `project` matches what the tick pins for
  the same window (shared oracle); outlook lookahead is date-bounded and stable.
- **`tests/test_chore_reconcile.py`** (new): `reconcile` as a pure unit — un-acted stale pin
  pruned; reminded pin kept; acted (completed/deferred) pin kept; `on_date < today` never in
  insert/prune; projected-but-unpinned inserted. All with plain value objects, no DB.
- Router tests: `activate` flips state and is one-way (409 on repeat); `rebalance` re-pins;
  both rate-limited (audit test picks them up).
- Alembic idempotency (CI downgrade/upgrade).

## Acceptance

`uv run pytest --no-cov` green; `make openapi` no diff; `uv run ruff check backend tests`
clean; `npx vue-tsc --noEmit` green; migration idempotent.

## Out of scope

Pass/cover/swap/availability actions (task 12), membership add/remove handling (task 13),
accountability provenance display (task 14). This task keeps existing `handoff`/`claim`
working against pinned rows unchanged.
