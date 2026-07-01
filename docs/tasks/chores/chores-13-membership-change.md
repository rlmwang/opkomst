# 13 — Membership change: removal static-patch, addition fold-in, disruption credit

**Layer:** backend (+ small frontend) · **Depends on:** 11 (projection/pins), 12 (actions,
availability, event kinds) · **Design refs:** §7 (folding in new volunteers; bootstrap;
"Removal is the asymmetric case"; incident catalogue), §14.5/§14.6.

## Goal

Handle volunteers joining and leaving a **running** roster with the right asymmetry:
**joining never rewrites a promise; leaving only rewrites the leaver's own promises.** The
projection already reflows for free (task 10 WRH); this task adds the *pinned-window*
behaviour and the communication.

## Addition (automatic, no button)

A new enrolment on a running roster:
- enters the projection immediately (task 10 handles the maths);
- is **not** pinned into the current window (existing promises stand);
- is folded into pins naturally as the horizon edge rolls forward (task 11 tick), so within
  `commit_horizon_days`.
- Details page shows them as **"joining — first turns from {date}"** where date = horizon
  edge; add a `pending` flag to `VolunteerSummaryOut` (true until they hold a pinned or past
  shift). No new mechanism, just the flag + copy.
- The organiser `rebalance` endpoint (task 11) is the opt-in "fold in now" path; ensure it
  re-pins the window from the projection **including** newly-enrolled volunteers, and is
  confirmation-gated in the UI ("reshuffles the next N days for M people").

## Removal (automatic, immediate)

When a volunteer leaves (leave endpoint) or is unenrolled:
- **Short term (pinned window): static patch.** Re-run WRH over the remaining pool for the
  window. Non-leaver pins are untouched (WRH guarantees it); only the leaver's own pinned
  shifts are reassigned to the next scorer and re-frozen, or → `open` + organiser flag if
  nobody eligible. Each inheritor gets an `inherited` event (pickup provenance + disruption
  credit, §7). Notify inheritors ("you've picked up {date}, covering for someone who left")
  via the existing reminder/mail path if they have email; always visible on their page.
  Inheritors may immediately **pass** (task 12) as an escape hatch.
- **Long term (projection): re-derive.** Nothing pinned, so WRH over the smaller pool is
  recomputed on read; the outlook becomes the genuine N-1 pattern and, because it reads the
  ledger, eases off the inheritors (repaying their disruption credit).
- **Past:** untouched; the leaver's completed/missed outcomes stay for stats with assignee
  nulled (existing `SET NULL`).

Implement removal reflow as an explicit `services/chores.py::on_volunteer_removed(roster,
volunteer)` called from the leave/unenroll handlers (not left to the next tick — coverage
must be immediate). Reuse the same `project`/`assign_occurrence` path as the tick so
short-term patch and long-term projection agree.

## Ledger writes

This task adds the `inherited` `ShiftEvent` emit (removal pickups) and confirms `covered`
(from task 12) both credit correctly. The near-term auto-reassign is the default; document
the `open`-for-claim alternative as not-chosen.

## Frontend

- `pending` badge + "first turns from {date}" on the details-page volunteer list.
- Inheritor's personal page shows the covered-for-leaver shift with its origin note.
- `make openapi` + types for the `pending` field.

## Tests

- **`tests/test_chore_membership.py`** (new): add on running roster → not in current pins,
  appears at edge within horizon, others unchanged; remove → only leaver's pins reassigned,
  all other pins byte-identical, inheritors get `inherited` events + credit; remove with no
  eligible → `open` + flagged; projection after removal = N-1 pattern and matches the pinned
  patch for overlapping dates (same-function invariant).
- Leak guard extended for `pending`.

## Acceptance

`uv run pytest --no-cov` green; `make openapi` no diff; `uv run ruff check backend tests`
clean; `npm run test` + `npx vue-tsc --noEmit` green; migration idempotent (only if a schema
change is introduced — none expected beyond task 12's).

## Out of scope

Accountability display of regular-vs-pickup (task 14, though this task emits the `inherited`
events it consumes).
