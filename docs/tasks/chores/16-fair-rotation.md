# Task 16 — Fair rotation: virtual-time fold replaces per-date WRH

**Layer:** backend only (pure core + tick shell). No API/schema change, no frontend
change, no migration.
**Depends on:** 15 (landed).
**Design:** `docs/design-chores.md` §7 "Deterministic assignment (virtual-time fair
rotation)" — already rewritten; this task makes the code match it. Rationale and the
measured WRH defects (turn clumping, non-proportional weights) live there, not here.

## The pure core (`backend/services/chore_assignment.py`)

Delete WRH wholesale (rule #1): `_score`, `assign_occurrence`, `_TWO64`, the blake2b
import. `net_credit`, `weight_from_ledger`, `summarize_accountability`, `CREDIT_SIGN`
stay untouched — the ledger is unchanged.

New, all pure (no DB, no clock, no RNG — history and state are just inputs):

- **State** is `dict[volunteer_id, float]` — the virtual clock `V`. Advancing volunteer
  `v` does `V[v] += 1.0 / weights.get(v, 1.0)`.
- **First touch seeds caught-up**: when an id first appears (as an eligible candidate or
  as a fixed assignee), it enters the state at `min(state.values(), default=0.0)` — a
  newcomer is owed nothing and owes nothing, no back-pay flood.
- `assign_date(demands, state, weights) -> dict[chore_id, list[volunteer_id]]` — one
  date, jointly. `demands` is `(chore_id, eligible_ids, count)` per chore, processed in
  **scarcity order** (fewest eligible first, then `chore_id`). Each slot picks
  `argmin (V[v], v)` over eligible volunteers not yet busy this date and advances the
  winner; a refill pass admits busy volunteers (never twice on the same chore) rather
  than leaving a slot open. Mutates `state` (callers thread it through the fold).
- `fold(days, state, weights) -> list[ProjectedAssignment]` (lives in
  `chore_projection.py`, replacing `project`) — walks `days` in date order. Each day
  carries the date's **fixed** assignments (already-materialised `occurrence → assignee`)
  and its **free** occurrences (enumerated by the pattern, no row yet). Per day: first
  advance every fixed assignee's clock and mark them busy, then `assign_date` the free
  slots. Returns assignments for every occurrence — fixed ones echo their assignee — so
  `reconcile` keeps its current contract unchanged.

Decisions an implementer needs, made here:

- **Fixed rows replay even when the pattern no longer produces them.** The fixed stream
  comes from actual `Shift` rows, merged into the day walk by `on_date`, independent of
  the current pattern. A pattern edit therefore never un-counts work already promised
  or done.
- **Shift rows, not ShiftEvents, drive the clocks.** Rebalance deletes un-acted pins;
  their orphaned `assigned` events (shift_id SET NULL) must not keep phantom clock
  advances alive. Events remain the ledger's source only.
- **Ghost assignees are harmless.** A fixed row whose assignee has left still advances
  that id's clock; the id is never eligible, so it is never picked. No filtering.
- **Availability** applies only to free picks (a fixed row is a commitment already made).
- **Ties** on `V` break by `volunteer_id`. Ties exist at cold start and immediately
  separate; no hash needed anywhere.

## The shell (`backend/services/chore_tick.py`, `backend/services/chores.py`)

- `project_range(db, roster, chores, start, end)` keeps its signature and its role as the
  one oracle, but folds **from `roster.starts_on`**, not from `start`: enumerate free
  occurrences over `[starts_on, end]`, load all of the roster's assignee-bearing `Shift`
  rows once as the fixed stream, fold, return only the assignments in `[start, end]`.
  Linear in days-since-start plus rows; rosters are small, no capping.
- `reassign_shift` (leaver re-cover, organiser hand-over fallback) replaces its WRH
  ranking: fold up to and including the shift's date (this shift's own row excluded from
  fixed), then pick the lowest-clock eligible volunteer not excluded, preferring one with
  no other shift that date, falling back to a busy one over leaving it open. Event kinds
  unchanged.
- Tick, `reconcile`, `rebalance_core`, activation: **no changes**. Rebalance already
  deletes un-acted pins before re-projecting; with pins gone from the fixed stream the
  fold reassigns them from fresh clocks, which is exactly the intended "fold pending
  volunteers in now".
- `chores.py` read-side (`chore_calendar`, `_personal_outlook`, `rebalance_preview_calendar`)
  all sit on `project_range` and need no changes.

## Tests

- `tests/test_chore_fairness.py` — rewrite the assignment half for the fold (ledger fold
  tests stay): determinism + input-order invariance; **even spacing** (weekly chore, 4
  volunteers, long run: never the same volunteer twice in a row, max gap ≤ pool size + 1);
  **proportional shares** (weight 0.5 lands `w/Σw` ± 10% — pin the old
  ~`w^(L-1)` distortion dead); **prefix consistency** (fold `[a,c]` == fold `[a,b]`, then
  continue over `(b,c]` from the returned state); fixed rows advance clocks (a volunteer
  with many materialised turns is rested next); newcomer seeds at pool-min (first turn
  within one rotation, nobody else's next turn moves earlier); same-day de-collision +
  shortfall double-booking + never-twice-on-one-chore (ported from task 15's tests);
  ghost assignee is a no-op for eligibility.
- `tests/test_chore_projection.py` — `test_project_is_window_independent` becomes the
  prefix-consistency test; keep de-collision; add: an occurrence with a fixed assignee is
  echoed, not recomputed.
- `tests/test_chore_tick.py` — scenarios re-anchor to the new assignments where they
  asserted specific assignees (they must change — that is the point); pins are honoured
  across ticks (running the tick daily over a fortnight never flips a pinned assignee);
  a covered shift visibly rests the coverer (their next projected turn moves later than
  the pre-cover projection).
- `tests/test_shift_events.py`, `test_chore_membership.py`, `test_chores_public.py` —
  behaviourally unchanged; fix any assignment-specific anchoring only.

## Landing

Suite green, `uv run ruff check backend tests`, no `make openapi` needed (no route or
schema change). Flip the README row to *landed* and delete this file in the feat commit.
