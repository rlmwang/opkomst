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

## The function: a pure core with a fully-enumerated input surface

The whole value of this task is a **pure function whose result depends on a precisely known,
minimal set of inputs**, so we can test it exhaustively and reason about it in isolation.
Weighted rendezvous (highest-random-weight) hashing, keyed on the **calendar occurrence**,
not on any running tally:

```
score(v) = weight(v) · H(v.id, chore.id, on_date)      # H → uniform (0,1), fixed hash
```

**The minimal input set (the core depends on ONLY these four):**

1. the occurrence key `(chore_id, on_date)`;
2. the **set** of eligible volunteer ids (already resolved: enrolled ∩ available);
3. a per-volunteer **weight** (`{id: float}`, default `1.0`) — the *only* channel through
   which history/state enters;
4. the count `people_per_shift`.

It must depend on **nothing else**: not `today`, not any other occurrence, not iteration
order, not the DB, not the wall clock, not an RNG. `H` and the tie-break are constants of the
function, not inputs.

The exact pure signature (module `services/chore_assignment.py`, zero I/O):

```python
def assign_occurrence(
    eligible: Iterable[str],          # volunteer ids, resolved (enrolled ∩ available)
    weights: Mapping[str, float],     # {id: weight}; missing id ⇒ 1.0
    *,
    chore_id: str,
    on_date: date,
    count: int,                        # people_per_shift
) -> list[str]:                        # the top-`count` ids, rank order (rank == slot index)
    ...
```

- **Slot index is the rank, not a hash input.** Score each eligible volunteer once per
  `(chore, on_date)`, sort descending, take the first `count`. So raising `count` only
  *appends* an assignee and never reshuffles the earlier slots. (No `slot_index` in `H`,
  no per-slot dedup loop.)
- `H` is a stable hash mapped to `(0,1)`: e.g. first 8 bytes of
  `blake2b(f"{v_id}|{chore_id}|{on_date.isoformat()}".encode())` over `2**64`. **No
  `random`, no salt, no process/machine variance.** Equal-score ties broken by `v_id`.
- `weight_from_ledger(net_credit: int) -> float` is a **bounded** map (clamp e.g.
  `[0.5, 2.0]`) so nobody is starved or saturated; default `1.0` when the ledger is empty.

**Purity boundary — keep the resolver out of the core.** All impure work lives in the
caller (tick / service): resolving `enrolled ∩ available` from the DB, and summing
`ShiftEvent` into `{id: net_credit}` then `{id: weight}`. The core receives only the plain
id-set + weight-map. This is what keeps the tested surface tiny and the reasoning local.

### Why WRH (record in the spec, it drives later tasks)

- **Deterministic + projectable:** score depends on the date, not on accumulated state, so
  "who is on three months out" is a pure computation with zero stored rows.
- **Robust to pattern edits:** keyed on the real date, so any date that still occurs after a
  `starts_on`/`period_weeks`/`cycle_slots` edit keeps its assignee.
- **Minimal disruption on membership change:** adding a volunteer moves only ~`1/(L+1)` of
  occurrences to them; removing one reassigns only *their* occurrences to the next scorer.
  Everyone else is untouched (task 11/13 rely on this).

## Deliverables

1. **Rewrite `services/chore_assignment.py`** as a pure, I/O-free module with the exact
   signature above:
   - `assign_occurrence(eligible, weights, *, chore_id, on_date, count) -> list[str]` —
     the top-`count` ids in rank order (rank == slot index); distinct by construction.
   - `weight_from_ledger(net_credit: int) -> float` — the bounded factor, unit-tested at
     its clamps.
   - Delete `pick_assignee`, its `random.Random` usage, and the `slot_index`/`avoid_same_day`
     parameters entirely (no backwards-compat shim).
2. **Ledger as a pure fold + a thin query** (design §7 "The pure core"):
   - `net_credit(events: Iterable[tuple[kind, volunteer_id]]) -> dict[str, int]` — a **pure**
     fold applying the credit signs from §7's event table. No DB; exhaustively testable by
     enumerating every `kind`'s contribution.
   - a thin impure wrapper (`services/chores.py` or `chore_ledger.py`) that queries the
     `ShiftEvent` rows for a roster and hands them to `net_credit`. Derived, no new column.
3. **Wire the tick** (`chore_tick.py`) to call `assign_occurrence` with current ledger
   weights instead of `pick_assignee`. Behaviour otherwise unchanged in this task (still
   eager horizon; task 11 changes *when* it runs).
4. Drop the `avoid_same_day` / cross-chore-load soft constraints for now; note in the spec
   they become an optional deterministic de-collision pass at pinning time (task 11), never
   in the projection.

## Tests

- **Rewrite `tests/test_chore_fairness.py`** (no RNG) — assert the properties that follow
  from the minimal input surface:
  - **Determinism / reproducibility:** a small known-answer vector (fixed ids + date →
    fixed assignee) so a hash change can never pass silently; same output on repeat calls.
  - **Order-independence:** permuting `eligible` yields the identical result (it is a
    function of the set, not the sequence).
  - **Rank-stability:** increasing `count` only appends assignees; the earlier slots are
    unchanged.
  - **Equal expected share** over many occurrences (statistical, generous tolerance).
  - **Minimal-disruption:** over a fixed date range, adding a volunteer changes only the
    expected fraction of occurrences and leaves every other assignment byte-identical; same
    for removal.
  - **No hidden inputs:** the result does not change with `today`/wall-clock (the function
    takes neither) and does not touch the DB — enforced structurally by the pure signature.
  - `weight_from_ledger` clamps at its bounds.
- `test_chore_tick` updated for the new call (assignments are now stable across two ticks).

## Acceptance

`uv run pytest --no-cov` green; `uv run ruff check backend tests` clean; migration
unchanged (no schema change this task).

## Out of scope

Commit horizon / projection (task 11), availability (task 13), the ledger *write* sites
beyond what 09 already emits (task 13 adds `covered`/`inherited`).
