# 06 — Shift generation + fairness (roster-tick) + shift actions

**Layer:** backend · **Depends on:** 05 · **Design refs:** §5 (Shift), §7 (generation,
fairness, handoff), §9.

## Goal

Materialise and fairly assign shifts on a rolling horizon, reconcile the past, and let
volunteers act on their shifts (done / hand off / claim). After this task the personal-page
payload and the organiser schedule/volunteers views show real data.

## Deliverables

1. **`backend/services/chore_assignment.py`** — the fairness function, **pure over its
   inputs** (eligible volunteer ids + their current loads + constraints), so it's
   seed-testable:
   ```python
   def pick_assignee(eligible: Sequence[str], loads: Mapping[str, int],
                     *, exclude: set[str], avoid_same_day: set[str],
                     rng: random.Random) -> str | None
   ```
   Greedy least-loaded: choose uniformly at random among min-load eligibles; apply
   `exclude` (the bailer on handoff) and `avoid_same_day` / previous-occupant as
   tie-break filters when alternatives exist. Returns `None` when no one is eligible.

2. **`backend/services/chore_tick.py`** — `run_tick(db, today)` per live roster:
   - **Extend**: for each chore, each date `D` in
     `[max(today, starts_on), today + HORIZON_DAYS]` capped by `ends_on`, where
     `recurrence.occurs_on(D, ...)` and no Shift exists, insert `people_per_shift` Shift
     rows (`status='open'`, `slot_index` 0..n-1).
   - **Assign**: for every `open` shift in the horizon, compute loads from existing
     `scheduled`+`done` shifts in the roster, call `pick_assignee`; on hit →
     `status='scheduled'`, set `volunteer_id`; on miss → leave `open`.
   - **Reconcile**: `scheduled` shifts with `on_date < today` and not done → `missed`.
   `HORIZON_DAYS` is a module constant (e.g. 28) — **not** an env var unless it needs to be
   configurable, in which case it goes through `Settings` (no bare default in code).

3. **CLI** — add `roster-tick` to `backend/cli.py` (one-shot, mirrors `dispatch`): build a
   session, `run_tick(db, date.today())`, log `event=cli_roster_tick rosters=N shifts=M`.

4. **Shift-action endpoints** (extend `backend/routers/chores_public.py`, edit-token-gated,
   rate-limited):
   - `POST /chores/by-token/{token}/shifts/{shift_id}/done` → assignee marks done
     (`status='done'`, `done_at=now`); 403 if the token's volunteer isn't the assignee.
   - `POST /.../shifts/{shift_id}/handoff` → bailer; shift → `open`, then immediately
     re-run `pick_assignee` with `exclude={bailer}`; if no one, stays `open`.
   - `POST /.../shifts/{shift_id}/claim` → take an `open` shift the volunteer is enrolled
     for → `status='scheduled'`, `volunteer_id=self`.

5. **Populate read payloads now that data exists:**
   - `PersonalPageOut.my_shifts` (upcoming `scheduled` for this volunteer) + `open_shifts`
     (claimable, enrolled chores).
   - Organiser `GET /chores/{id}/schedule` → upcoming shifts + assignee `display_name` +
     completion stats (done / missed / scheduled counts).
   - Organiser `GET /chores/{id}/volunteers` → real per-volunteer **load** (and chores
     enrolled) — still **no email/token**.
   - `RosterOut.volunteer_count` now reflects reality.

6. **`make openapi`**.

## Tests

- **`tests/test_chore_fairness.py`** — `pick_assignee` with a seeded `Random`: equal loads
  → balanced over many draws; ties resolved within min-load set only; `exclude` honoured;
  `None` when empty; no same-day double when avoidable.
- **`tests/test_chore_tick.py`** — weekly + biweekly rosters: correct dates materialised
  (uses `occurs_on`), idempotent (second tick adds nothing), horizon + `ends_on` respected,
  reconcile flips past `scheduled`→`missed`, leave (SET NULL) reopens future shifts on next
  tick.
- **Shift-action tests** in `test_chores_public.py` — done by assignee only; handoff
  reassigns/excludes; claim only when `open` + enrolled.

## Acceptance

- `uv run pytest --no-cov` green; `make openapi` no diff; `uv run ruff check backend tests`
  clean.

## Out of scope

Reminder emails (08). Public UI (07) — but the payloads it will consume are finished here.
