# R4 — Backend refactor: public slug/token resolver

**Layer:** backend (refactor) · **Run before:** 05 · **Consumed by:** 05 (chores public
router), 06 (shift-action endpoints).

## Goal

The public routers each hand-roll the same two lookups: resolve a live entity by slug
(404/410 if missing/archived), and resolve a submission by edit-token hash then guard on
its parent's state. `_signup_by_token` / `_submission_by_token` (×3) are ~90% identical;
the only variance is the parent model and the events-only `ends_at` check. Extract two
helpers, migrate the three public routers, then chores reuses them. No behaviour change.

## Deliverables

1. **`backend/services/public_access.py`** (new):
   - `resolve_by_slug(db, model, slug, *, allow_archived=False, gone_detail)` — query by
     slug; 404 if absent; 410 (with `gone_detail`) if `archived_at` set and not allowed.
   - `resolve_by_token(db, submission_model, token, *, parent_model, parent_fk, gone_detail,
     extra_guard=None)` — hash the token (`edit_token.hash_edit_token`), look up the
     submission (404 if absent), load the parent (410 if absent/archived), run optional
     `extra_guard(parent)` (e.g. events: `parent.ends_at <= now_wallclock()` → 410), return
     the submission. Keep the user-facing 404/410 copy identical to today's strings.
2. **Migrate** `signups.py`, `forms_public.py`, `datepolls_public.py` onto the helpers:
   - signups → `resolve_by_token(..., parent_model=Event, parent_fk=Signup.event_id,
     extra_guard=lambda e: e.ends_at <= now_wallclock())`.
   - forms/datepolls → `resolve_by_token(...)` with no `extra_guard`.
   - replace the per-router `_resolve_form`/`_resolve_datepoll` slug helpers with
     `resolve_by_slug`.

## The guard

Identical status codes and message strings (these are user-visible public copy — don't
change them). Existing public-router tests pass **unedited**.

## Tests

- `uv run pytest --no-cov` green with no edits to signups/forms/datepolls public tests.
- Add `tests/test_public_access.py` (token 404; archived parent 410; events `ends_at`
  guard 410; happy path returns the submission).

## Acceptance

- Full suite green; `uv run ruff check backend tests` clean.

## Out of scope

The chores public router (task 05) and shift-action endpoints (task 06) — they consume
these helpers (the chore "parent" is the `Roster`, reached via `Volunteer.roster_id`, and
for shift actions via the shift's chore→roster).
