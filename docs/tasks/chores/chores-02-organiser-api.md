# 02 — Organiser CRUD API

**Layer:** backend · **Depends on:** 01, R2 (archivable CRUD helper) · **Design refs:**
§4, §9 (organiser side), §10 (recurrence-shrink rule for validation).

## Goal

Full organiser-side CRUD for rosters + their nested chores, chapter-scoped, rate-limited,
with OpenAPI regenerated and router/access tests. After this task an organiser can create,
list, edit, archive, restore, and delete rosters via the API. Volunteer/schedule read
endpoints are deferred (no data yet) to tasks 05/06.

## Deliverables

Mirror `backend/routers/datepolls.py` + `backend/schemas/datepolls.py` (parent + nested
config children is the same shape).

0. **First, relocate `Locale`.** It currently lives in `backend/schemas/events.py:12`
   (`Locale = Literal["nl","en"]`) but is a shared primitive. Move it to
   `backend/schemas/common.py` (next to `DisplayName`/`InstagramHandle`/`LowercaseEmail`)
   and update the events/forms/datepolls schema imports. Behaviour-neutral; `make openapi`
   shows no diff. (Cleanest-design rule: a shared type belongs in `common.py`.)
1. **`backend/schemas/chores.py`** — reuse `common.Locale`, `common.InstagramHandle`,
   `common.DisplayName` where relevant:
   - `ChoreIn` — `id: str | None` (null=new, set=existing on update, like
     `FormQuestionIn`), `name` (1..200), `description?` (≤2000), `cycle_slots: list[int]`
     (unique, sorted, each `< 7*period_weeks` — validated against the parent's k in the
     router/parent validator), `people_per_shift` (1..N), `emoji?`.
   - `RosterCreate` — `chapter_id`, `name`, `description?`, `image_artist_instagram`,
     `locale`, `location?` + `latitude?` + `longitude?`, `period_weeks` (≥1),
     `anchor_monday: date | None`, `starts_on: date`, `ends_on: date | None`,
     `reminder_enabled` (default True), `reminder_days_before` (default 1),
     `chores: list[ChoreIn]`.
     Cross-field validation: if `period_weeks > 1` then `anchor_monday` is required and
     must be a Monday; every chore's `cycle_slots` value `< 7*period_weeks`. On update,
     **shrinking `period_weeks` drops out-of-range slots** (clamp server-side; the UI warns
     — task 04) rather than rejecting.
   - `RosterOut` — spine + `id`, `slug`, `archived` (computed), `chapter_name`,
     `image_url`, `chores: list[ChoreOut]`, `volunteer_count` (0 for now).
   - `PublicRosterOut` — the public projection (no chapter/timestamps); used in task 05.

2. **`backend/routers/chores.py`** — `/api/v1/chores`, `require_approved`, every mutator
   `@limiter.limit(...)`:
   - `POST /chores` (create Roster + nested Chores; `new_slug`; `chapter_id` validated via
     `access.list_filter`/membership check, like events).
   - `GET /chores` (active, `roster_scope_filter`, optional `?chapter_id=`).
   - `GET /chores/archived`.
   - `GET /chores/{id}` (single, for edit prefill; `access.get_roster_for_user`).
   - `PUT /chores/{id}` (update Roster + reconcile Chores by `id`: upsert/renumber
     `ordinal`, delete removed — mirror the Form question reconcile).
   - `POST /chores/{id}/archive`, `POST /chores/{id}/restore`,
     `DELETE /chores/{id}` (archived-only) — each via the **R2 `crud` helper**
     (`crud.archive`/`restore`/`hard_delete`); the handler is just access lookup → helper →
     projection.
   - **Image endpoint** using the shared `image_svc.replace_entity_image(folder="chores")`
     helper — mirror `routers/forms.py` / `routers/datepolls.py` (~28 lines), **not**
     `events.py` (which predates the helper and inlines 59 lines; it's the outlier). The
     frontend `useImageUpload(resource)` composable is already generic, so the client side
     needs no new code.
   Register the router in `backend/main.py`.

3. **`make openapi`** — regenerate `openapi.json` + `frontend/src/api/schema.ts`.

## Tests

- **`tests/test_chores_router.py`** — create→list→get→update (chore add/remove/reorder)
  →archive→restore→delete happy paths; chapter scoping (user can't see/modify another
  chapter's roster → 404); `period_weeks>1` without Monday anchor → 422; out-of-range
  `cycle_slots` on create → 422; shrink-k clamps slots on update.
- `tests/test_rate_limits_audit.py` should pass automatically (it scans for the decorator
  on every mutator) — confirm.
- `tests/test_permissions.py` style: unapproved/non-member access denied.

## Acceptance

- `uv run pytest --no-cov` green (full suite — schema-drift/openapi check included).
- `make openapi` produces no further diff.
- `uv run ruff check backend tests` clean.
- Migration unchanged from task 01 (no new model fields here).

## Out of scope

`GET /chores/{id}/volunteers` and `/schedule` (no data — tasks 05/06). No public routes.
No mail.
