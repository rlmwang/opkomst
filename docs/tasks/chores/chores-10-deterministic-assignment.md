# 10 — Deterministic assignment (weighted rendezvous hashing) + favour ledger

**Layer:** backend · **Depends on:** 06 (shifts + tick), 09 (`ShiftEvent`) ·
**Design refs:** §7 (deterministic assignment, fairness), §14.4.

## Goal

Replace the greedy-least-loaded-with-**unseeded-random**-tie-break assignment
(`services/chore_assignment.py::pick_assignee`) with a **pure, deterministic** function so
the schedule can be projected to any future date and never changes non-deterministically
between runs. This is the foundation task 11 builds the projection on: if assignment is not
a pure function of `(pattern, eligible set, ledger, occurrence key)`, nothing downstream can
be projected.

## The function

Weighted rendezvous (highest-random-weight) hashing, keyed on the **calendar occurrence**,
not on any running tally:

```
score(v) = weight(v) · H(v.id, chore.id, on_date, slot_index)      # H → uniform (0,1)
```

- Assignee(s) for an occurrence = the top `people_per_shift` distinct volunteers by score,
  among those enrolled in the chore and available on that date (availability lands in task
  13; until then the available set == the enrolled set).
- `H` is a stable hash mapped to `(0,1)` (e.g. take the first 8 bytes of
  `blake2b(f"{v.id}|{chore.id}|{on_date.isoformat()}|{slot_index}")`, divide by `2**64`).
  **No `random` module, no RNG state.** Ties (equal float) broken by `v.id` for total
  determinism.
- `weight(v) = base · ledger_factor(v)` where base is equal for all volunteers and
  `ledger_factor` is a **bounded** function of net favour credit (task 13 populates the
  ledger; here define the shape and default `ledger_factor == 1.0` when the ledger is
  empty). Bound it (e.g. clamp to `[0.5, 2.0]`) so no volunteer is ever fully starved or
  saturated.

### Why WRH (record in the spec, it drives later tasks)

- **Deterministic + projectable:** score depends on the date, not on accumulated state, so
  "who is on three months out" is a pure computation with zero stored rows.
- **Robust to pattern edits:** keyed on the real date, so any date that still occurs after a
  `starts_on`/`period_weeks`/`cycle_slots` edit keeps its assignee.
- **Minimal disruption on membership change:** adding a volunteer moves only ~`1/(L+1)` of
  occurrences to them; removing one reassigns only *their* occurrences to the next scorer.
  Everyone else is untouched (task 11/13 rely on this).

## Deliverables

1. **Rewrite `services/chore_assignment.py`** as a pure module:
   - `assign_occurrence(eligible, *, chore_id, on_date, slot_index, count, weights) ->
     list[str]` returns the ordered top-`count` volunteer ids (distinct).
   - `weight_from_ledger(net_credit: int) -> float` — the bounded factor, unit-tested at
     its clamps.
   - Delete `pick_assignee`'s RNG signature and its `random.Random` usage entirely (no
     backwards-compat shim).
2. **Ledger accessor** in `services/chores.py` (or a small `chore_ledger.py`): one grouped
   query over `ShiftEvent` → `{volunteer_id: net_credit}` using the credit signs in §7's
   event table. Derived, no new column.
3. **Wire the tick** (`chore_tick.py`) to call `assign_occurrence` with current ledger
   weights instead of `pick_assignee`. Behaviour otherwise unchanged in this task (still
   eager horizon; task 11 changes *when* it runs).
4. Drop the `avoid_same_day` / cross-chore-load soft constraints for now; note in the spec
   they become an optional deterministic de-collision pass at pinning time (task 11), never
   in the projection.

## Tests

- **Rewrite `tests/test_chore_fairness.py`** (no seeded RNG): determinism (same inputs →
  same output, run twice); equal expected share over many occurrences (statistical, with a
  generous tolerance); the **minimal-disruption property** — assign a fixed date range,
  add a volunteer, assert only the expected fraction of occurrences changed hands and all
  others are identical; same for removal; `weight_from_ledger` clamps.
- `test_chore_tick` updated for the new call (assignments are now stable across two ticks).

## Acceptance

`uv run pytest --no-cov` green; `uv run ruff check backend tests` clean; migration
unchanged (no schema change this task).

## Out of scope

Commit horizon / projection (task 11), availability (task 13), the ledger *write* sites
beyond what 09 already emits (task 13 adds `covered`/`inherited`).
