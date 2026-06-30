# 01 — Data model + recurrence helper + access scope

**Layer:** backend · **Depends on:** R1 (`OrgEntityMixin`) · **Design refs:** §3, §4, §5,
§7 (generation math).

## Goal

Land the five tables, the chapter-scoped access helpers, and the pure recurrence function,
with model-level + recurrence unit tests. No routes, no mail, no shift generation yet.

## Deliverables

Mirror `backend/models/datepolls.py` (closest shape: parent + config children + public
submissions).

1. **`backend/models/chores.py`** — five models, all `UUIDMixin + TimestampMixin`:
   - **`Roster`** — inherit the spine from **`OrgEntityMixin`** (R1): that supplies `slug`,
     `name`, `image_url`, `image_artist_instagram`, `locale`, `created_by`, `chapter_id`,
     `archived_at`. Declare only the Roster-specific columns here: `description?`,
     `reminder_enabled` (bool default True), `location?` + `latitude?` + `longitude?`, and
     the `ix_rosters_archived_chapter` Index in `__table_args__` (per-model, like the
     others). Plus recurrence:
     `period_weeks` (int, default 1), `anchor_monday` (Date?), `starts_on` (Date),
     `ends_on` (Date?), `reminder_days_before` (int, default 1). *(Shifts are date-only —
     no clock time — so reminders are days-before, not hours-before; see task 08.)*
     Index `ix_rosters_archived_chapter` on `(archived_at, chapter_id)`.
   - **`Chore`** — `roster_id` (FK CASCADE, indexed), `name`, `description?`, `ordinal`
     (int), `cycle_slots` (JSON list[int]), `people_per_shift` (int default 1), `emoji?`.
   - **`Volunteer`** — `roster_id` (FK CASCADE, indexed), `display_name?`,
     `encrypted_email` (LargeBinary?), `email_reminders` (bool default False),
     `edit_token_hash` (Text, unique, indexed). *(No writes to `encrypted_email` happen in
     this task; column only.)*
   - **`Enrollment`** — composite PK `(volunteer_id, chore_id)`, both FK CASCADE. (Mirror
     `user_chapters` in `models/users.py`.)
   - **`Shift`** — `chore_id` (FK CASCADE, indexed), `on_date` (Date), `slot_index` (int),
     `volunteer_id` (FK `volunteers.id` **SET NULL**), `status`
     (`Literal['scheduled','done','open','missed']`, CHECK), `done_at?`,
     `reminder_sent_at?`. `UniqueConstraint(chore_id, on_date, slot_index)`. Index on
     `(chore_id, on_date)` for sweep/reads.

2. **`backend/services/recurrence.py`** — the pure cycle function (no DB):
   ```python
   def occurs_on(d: date, *, cycle_slots: Sequence[int], period_weeks: int,
                 anchor_monday: date | None) -> bool
   ```
   - k=1: `d.weekday() in cycle_slots`.
   - k>1: requires `anchor_monday`; `False` if `d < anchor_monday`; else
     `((d - anchor_monday).days % (7*period_weeks)) in cycle_slots`.
   Keep it the single source of truth for "does this chore fall on this date".

3. **`backend/services/access.py`** — add, mirroring the Event helpers exactly:
   `get_roster_for_user(db, roster_id, user) -> Roster` (404 not 403 on out-of-scope) and
   `roster_scope_filter(db, user)` (wraps `scope_filter(db, user, Roster.chapter_id)`).

4. **Alembic migration** — one autogenerate:
   `uv run alembic -c backend/alembic.ini revision --autogenerate -m "chores tables"`.
   Review it; confirm FKs/indexes/CHECK landed.

## Validation rules (enforce at the model/service layer that has no schema yet only where
structural; the rest move to schemas in task 02)

- `anchor_monday`, when set, is a Monday. Document the Mon=0 convention in the model
  docstring.
- `cycle_slots` values are `0 .. 7*period_weeks - 1`.

## Tests

- **`tests/test_chore_recurrence.py`** — the `occurs_on` matrix: weekly weekday hits; k=2
  alternating weeks; dates before anchor excluded; whole-day modulo wrap at the cycle
  boundary. Pure, no DB, fast.
- **`tests/test_chore_models.py`** — create a Roster + Chore + Volunteer + Enrollment +
  Shift via a session; assert CASCADE on roster delete, SET NULL on volunteer delete
  (shift survives with `volunteer_id IS NULL`), and the `(chore_id, on_date, slot_index)`
  uniqueness.

## Acceptance

- `uv run pytest --no-cov tests/test_chore_recurrence.py tests/test_chore_models.py` green.
- `alembic downgrade base && alembic upgrade head && alembic upgrade head` clean (the CI
  idempotency check).
- `uv run ruff check backend tests` clean.

## Out of scope (later tasks)

Routers, schemas, OpenAPI, any `encrypted_email` writes, shift generation, mail. Models
exist but nothing populates Volunteer/Shift yet.
