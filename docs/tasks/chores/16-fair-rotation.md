# Task 16 — Fair rotation: replace per-date WRH with a virtual-time fold

**Layer:** backend (pure core + shell; no API/schema change, frontend untouched)
**Depends on:** 15

## Problem, measured

WRH scores every date independently, so one volunteer's turn dates are an i.i.d.
sample: gaps are geometrically distributed, and clumping is *expected*, not rare.
Simulated on the real `assign_occurrence` (4 volunteers, one weekly chore, 104
occurrences):

- **~20% of consecutive occurrences go to the same person** (back-to-back turns);
- **max gaps of 17–19 weeks** — a volunteer does two in a row, then nothing for
  four months. Exactly the reported behaviour, inherent to the algorithm.

Worse, the favour-ledger weight is **not proportional** under WRH. A weight `w`
against `L-1` unit-weight volunteers wins `∫ (min(wx,1))^(L-1) dx`, which is
polynomial in the pool size, not `w/(w+L-1)`:

| pool L | weight 0.5 gets | should get | weight 2.0 gets | should get |
|---|---|---|---|---|
| 3 | 8.3% | 20% | 67% | 50% |
| 4 | 3.1% | 14% | 62% | 40% |
| 6 | 0.5% | 9% | 58% | 29% |

The "gentle, bounded tilt" (§7) is actually near-starvation/saturation: one
covered shift (credit +1 → weight 0.9) shifts a 6-person share from 16.7% to
~9%, so the self-correction wildly overshoots and then oscillates.

## Alternatives considered

1. **Strict round robin over the occurrence index** (`k mod L`): perfect spacing,
   but any join/leave/pattern edit renumbers the whole future — the churn the
   §7 redesign was built to avoid — and weights don't fit.
2. **Low-discrepancy sequences** (golden-ratio phases per volunteer): good
   spacing, but index-based like (1), same churn, and weight support is awkward.
3. **Smoothing pass at pin time only**: keeps WRH for the outlook, fixes spacing
   only inside the window → confirmed and outlook stop reading one oracle (the
   same reason task 15 rejected pin-time de-collision), and the weight
   distortion stays.
4. **Virtual-time fair scheduling** (stride scheduling / WFQ; the smooth-WRR
   family used by nginx and OS schedulers): assignment becomes a **date-ordered
   fold**. Each volunteer carries a virtual time `V`; each occurrence goes to
   the eligible, same-day-free volunteer with the lowest `(V, volunteer_id)`,
   whose `V` then advances by `1/weight`. **Chosen.**

Simulated on the real shape (two chores, Wed+Fri, 4 volunteers, one at weight
0.5, 312 occurrences): **zero** back-to-back turns, max gap 12 days (19 for the
half-weight volunteer — by design, they're owed a rest), and shares land exactly
proportional (0.144 vs expected 0.143; others 0.285 vs 0.286). Same result on
the single-chore case: max gap 4 occurrences instead of 19.

## Design

### The pure core (`chore_assignment.py`, replacing WRH wholesale — rule #1)

The fold is exactly as pure as the per-date rule was — deterministic over plain values,
no DB, no clock, no RNG. Materialised history and the rotation state are simply more
*inputs*; nothing about the purity boundary or the testing story changes.

- `RotationState = dict[volunteer_id, float]` — virtual time per volunteer.
- One pick: `argmin (V[v], v)` over the candidates; winner's `V += 1/weight(v)`
  (weight from the ledger as today, default 1.0). Deterministic; ties only at
  cold start and resolve by id, after which `V`s separate.
- `assign_date(demands, state, weights, ...)`: slots of one date are picked in
  scarcity order (fewest eligible first, then chore_id), each excluding
  volunteers already busy that date; a refill pass admits busy volunteers rather
  than leaving a slot open (task 15 semantics, unchanged). Because `V` is
  **global per volunteer across chores**, the fold also spaces one person's
  turns *across* chores and converges everyone's total load — the aggregate
  cross-chore balancing §7 listed as out of scope falls out for free.
- `fold(dated occurrences, fixed, eligible_by_chore, weights, state)`: walk dates
  in order; an occurrence present in `fixed` (a frozen past shift or a kept pin)
  just advances its actual assignee's `V`; the rest are picked. Returns the
  assignments for the free occurrences.

### The shell (`chore_tick.py` / `chores.py` service)

- `project_range` seeds the fold with **reality**: every existing Shift row with
  an assignee (frozen past + pinned window, whatever their provenance — WRH
  history, claims, covers, organiser hand-overs) enters as `fixed`, from
  `roster.starts_on` up to the projection end. Past eligibility history is a
  non-issue: past dates are always `fixed` rows. Someone who just covered three
  shifts has a high `V` and is automatically rested — the fold *is* short-term
  self-correction, while the ledger keeps the long-term share tilt.
- The tick/reconcile/rebalance pipeline is unchanged: pins are honoured, the
  fold treats them as fixed points, so pinning day-by-day and the whole-window
  outlook still agree (the window-independence test becomes a **prefix
  consistency** test: folding `[a,c]` equals folding `[a,b]` then `[b,c]`).
- `reassign_shift` (leaver re-cover) ranks by the folded `V` at the shift's date
  instead of a WRH ranking; same free-that-day preference.
- A brand-new volunteer first appears in the fold at the projection start with
  `V = ` the pool's current minimum — no back-pay flood; they take their first
  turn within about one rotation, and still enter pins only as the horizon
  rolls (or via "Rebalance now"), exactly as §7 promises.

### The honest trade-off (this reverses a §7 decision — say so in the doc)

WRH's rendezvous property meant a join/leave moved only ~`1/(L+1)` of future
*dates*. A sequential fold reshuffles the **tentative** zone more broadly after
a membership or pattern change. What actually matters is protected regardless:
the commit horizon is pinned and never reshuffles, the outlook is explicitly
labelled "may change", and a newcomer's fold-in stays bounded. We trade
stability of the far tentative outlook for correct spacing and truly
proportional fairness — the product promise ("dividing chores fairly and
evenly") is the latter.

`docs/design-chores.md` §7 is rewritten accordingly: assignment section, the
fairness section (proportional weights — the `[0.5, 2.0]` clamp finally means
"half share … double share"), minimal-disruption paragraph, pure-core table.

## Tests

- Rewrite `tests/test_chore_fairness.py` for the fold: determinism, input-order
  invariance, **no back-to-back turns when `L ≥ 3`** on a weekly chore, **max
  gap ≤ 2·rotation**, exact-share convergence for weighted volunteers (±10%),
  same-day de-collision + shortfall (kept from task 15), prefix consistency.
- `test_chore_projection.py`: window tests become prefix-consistency tests;
  fixed rows advance the state (a volunteer with many fixed turns is rested).
- `test_chore_tick.py`: pins honoured; newcomer folds in without a flood;
  existing scenario tests re-anchored (assignments change — they must, that's
  the point).
