# Task 15 — Same-day de-collision: joint assignment per date

**Layer:** backend (pure core + tick; no API/schema change, no frontend change)
**Depends on:** 10, 11

## Problem

`chore_projection.project()` assigns each `(chore, date)` group independently through
`assign_occurrence`. The WRH score is keyed on `(volunteer, chore, date)`, so the scores
for two different chores on the same date are independent draws — the volunteer who tops
chore A's ranking on a date can also top chore B's. On a roster where several chores share
a weekday, one volunteer regularly draws two or more different chores on the same day
while others draw none. That contradicts the product's core promise (dividing chores
fairly and evenly); the design doc lists it under §7 "Known limitations".

The single-shift path has the same blind spot: `chore_tick._occupants` (used by
`reassign_shift` → `cover_orphaned_shifts` when a volunteer leaves) only excludes people
on other slots of the *same* occurrence, so re-covering a leaver's shifts can also stack
two chores on one person's day.

## Design: assignment becomes a pure function of the *date*, not the `(chore, date)` pair

The design doc sketched a de-collision pass "applied only at pinning time". We do better:
because a collision is by definition same-day, the natural assignment unit is the **date**,
and a joint assignment over all chores occurring on one date is still a pure,
window-independent function. Putting it inside `project()` (rather than a pin-time pass)
preserves the §7 invariant that confirmed and outlook read the same oracle — the outlook a
volunteer sees never shows a double-booking that pinning would then silently undo. And it
stays projectable to infinity: any window is still a per-date map.

New pure function in `chore_assignment.py`:

```
assign_date(demands, weights, *, on_date) -> dict[chore_id, list[volunteer_id]]
# demands: sequence of (chore_id, eligible_set, count)
```

Greedy matching over the existing WRH scores (the hash key `(volunteer, chore, date)` is
unchanged):

1. Score every eligible `(volunteer, chore)` pair exactly as today.
2. Order all pairs by `(-score, volunteer_id, chore_id)` — total order, so the result is
   deterministic and invariant to input order.
3. Walk down the list: take a pair when its chore still has unfilled slots **and** the
   volunteer holds no assignment on this date yet. Per chore, acquisition order is the
   slot index (rank == slot, as before).
4. Shortfall pass: chores still short of `count` refill from the same ordered list,
   now admitting volunteers already booked on another chore this date (never twice on the
   same chore). Coverage beats strict no-collision — a slot only projects to `None` (open)
   when no eligible volunteer remains at all.

Properties (each asserted in `tests/test_chore_fairness.py`):

- **Deterministic + set-order invariant** — the ordering key is `(score, ids)` only.
- **Window independence** — `project` over `[a, b]` restricted to a date equals projecting
  that date alone; pinning day-by-day and projecting the whole window agree.
- **No avoidable same-day double-booking**; when the pool is smaller than the day's total
  demand, slots are double-booked rather than left open.
- **Distinct assignees within one chore/date** (unchanged).
- **Single-chore dates are byte-identical to the current output** — greedy matching over
  one chore degenerates to top-`count` ranking, so the common case doesn't reshuffle when
  this lands, and the rendezvous minimal-disruption property is untouched there.
- **Bounded churn under membership change** — a joint assignment lets a contested
  volunteer's move cascade within a date, but never across dates; keep a churn test with
  the same tolerance style as the existing WRH stability tests.

## Changes

- `backend/services/chore_assignment.py` — add `assign_date` (pure). `assign_occurrence`
  stays as the single-shift primitive (`reassign_shift` still needs it).
- `backend/services/chore_projection.py` — `project()` groups occurrences by `on_date`
  and calls `assign_date` once per date; the per-`(chore, date)` loop goes away.
- `backend/services/chore_tick.py` — `_occupants` widens to *all* scheduled shifts of the
  roster on that date (join `Chore` on `roster_id`), so `reassign_shift` /
  `cover_orphaned_shifts` won't create a same-day stack when re-covering a leaver's
  shifts. Fallback unchanged: if everyone eligible is busy that day, the highest-ranked
  eligible gets it anyway (coverage first).
- `docs/design-chores.md` §7 — rewrite the assignment section to specify per-date joint
  assignment; the "Known limitations" paragraph shrinks to the one remaining true
  limitation (no global cross-chore *aggregate* load levelling — the favour ledger remains
  the equalizer over time).

Existing pinned windows may contain collisions from the old projection; promises stand
(§7). They wash out as the horizon rolls, or immediately via the organiser's "Rebalance
now". No migration, no data change.

## Non-goals

- **Cross-date load shaping** (e.g. spacing one volunteer's turns across a week). Any
  cross-date dependence would reintroduce sequence-dependence into the projection — the
  exact flaw the §7 redesign removed. Fairness across dates stays WRH expected share +
  ledger.
- **Blocking voluntary same-day claims.** A volunteer who *chooses* to claim or cover a
  second chore on a day they already serve is helping, not a scheduling defect.

## Tests

- `tests/test_chore_fairness.py`: the property list above for `assign_date`.
- `tests/test_chore_tick.py`: a two-chores-same-weekday roster ticks to a window with no
  avoidable same-day double-booking; a 2-chores/1-volunteer roster double-books rather
  than leaving slots open; `cover_orphaned_shifts` after a leave prefers a volunteer who
  is free that day.
