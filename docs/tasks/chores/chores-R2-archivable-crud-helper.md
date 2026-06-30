# R2 — Backend refactor: archivable CRUD helper

**Layer:** backend (refactor) · **Run before:** 02 · **Consumed by:** 02 (chores router).

## Goal

The archive / restore / delete handlers in `routers/events.py`, `forms.py`, `datepolls.py`
are ~98% byte-identical (~150 duplicated lines). Extract the shared middle into a helper,
migrate the three routers, then the chores router reuses it. No behaviour change.

## Deliverables

1. **`backend/services/crud.py`** (new) — operate on an already-fetched, access-checked
   model instance with an `archived_at` column:
   - `archive(db, entity, *, log_event) -> None` — 409 if already archived; set
     `archived_at = now(UTC)`; commit; refresh; structured log.
   - `restore(db, entity, *, log_event) -> None` — 409 if not archived; clear
     `archived_at`; commit; refresh; log.
   - `hard_delete(db, entity, *, log_event) -> None` — 409 if **not** archived
     (delete is archived-only); delete; commit; log.
   Keep the access lookup (`access.get_*_for_user`) and the entity-specific `to_out`
   projection **in the routers** — only the archived_at flip + guards + commit + log move
   into the helper.
2. **Migrate** the archive/restore/delete handlers in all three organiser routers to call
   the helper. Each handler becomes: access lookup → helper call → return projection.

## The guard

No behaviour change: same status codes (409 already/not-archived), same side effects, same
log events. The existing router tests are the spec — they pass **unedited**.

## Tests

- `uv run pytest --no-cov` green with no edits to the events/forms/datepolls router tests.
- Optionally add a focused `tests/test_crud_helper.py` (archive twice → 409; delete a live
  entity → 409; restore a live entity → 409).

## Acceptance

- Full suite green; `uv run ruff check backend tests` clean.
- `tests/test_rate_limits_audit.py` still green (handlers keep their `@limiter.limit`).

## Out of scope

List/single-get handlers (they vary by sort order/projection — not worth forcing). The
chores router (task 02) consumes this helper for its own archive/restore/delete.
