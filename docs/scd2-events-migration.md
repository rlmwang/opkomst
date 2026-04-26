# SCD2 migration for the `events` table

Status: **planned**, not yet executed. Scope is locked in below; execute when ready.

## Decisions (locked)

1. **Strict SCD2**, full refactor. No backward-compat fallback paths.
2. **`Signup.event_id` and `FeedbackToken.event_id` and `FeedbackResponse.event_id` switch to point at `Event.entity_id`** (the stable logical id), not the per-version row id. A signup belongs to the event-as-a-concept, not a specific revision.
3. **No per-event history page.** SCD2 here is a database-engineer audit tool, not a user-facing feature. The columns capture what we need; surfacing them is out of scope.
4. **Port the `scd2-safety` pre-commit hook** from horeca-backend so any future bare `db.query(Event)` without a `valid_until IS NULL` filter is flagged at commit time.

## Schema changes

`Event` gains five columns. None are nullable after backfill except `valid_until`:

```python
class Event(...):
    # Existing: id (uuid7 PK), slug, name, topic, location, latitude, longitude,
    # starts_at, ends_at, source_options, questionnaire_enabled, archived_at,
    # created_by, created_at, updated_at.
    entity_id: Mapped[str]                         # stable across versions
    valid_from: Mapped[datetime]                   # when this version became current
    valid_until: Mapped[datetime | None]           # NULL on the current version
    changed_by: Mapped[str]                        # FK -> users.id
    change_kind: Mapped[str]                       # "created" | "updated" | "archived" | "restored"
```

`entity_id` is the stable logical id. The first version self-references: `entity_id = id`. Subsequent versions share the original's `entity_id`.

`slug` stays on every row (copied across versions; never changes for a given event).

## Foreign-key changes

| Table | Column | Before | After |
|---|---|---|---|
| `signups` | `event_id` | `events(id)` | `events(entity_id)` |
| `feedback_tokens` | `event_id` | `events(id)` | `events(entity_id)` |
| `feedback_responses` | `event_id` | `events(id)` | `events(entity_id)` |

`entity_id` is not currently unique across all `events` rows (multiple versions share it), so the FK target is non-standard. Two options:
- **(a)** Drop the FK constraint, keep the column and the index. Simpler, accepts that referential integrity is enforced only by code.
- **(b)** Add a partial unique index `UNIQUE (entity_id) WHERE valid_until IS NULL` and FK against that. Cleaner, but composite-FK-with-partial-unique support varies by dialect.

**Pick (a)** for opkomst's scale — drop the FK, keep the index, enforce in code via the `current()` helper. Document the choice next to the column.

## Helpers

New module `backend/services/scd2.py`:

```python
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session
from uuid_utils import uuid7
from ..models import Event

# Fields that travel forward when a new version is minted. Anything not
# in this list (id, entity_id, valid_from, valid_until, changed_by,
# change_kind, created_at, updated_at) is set freshly on each version.
_MUTABLE_FIELDS = (
    "slug",
    "name",
    "topic",
    "location",
    "latitude",
    "longitude",
    "starts_at",
    "ends_at",
    "source_options",
    "questionnaire_enabled",
    "archived_at",
    "created_by",
)

def current(query: "Query[Event]") -> "Query[Event]":
    """Filter an Event query to current versions only."""
    return query.filter(Event.valid_until.is_(None))

def current_event(db: Session, ref: str) -> Event | None:
    """Resolve to the current Event row by either row id or entity_id.
    Both forms accepted so URLs minted from older list snapshots still work."""
    return current(db.query(Event)).filter(
        or_(Event.id == ref, Event.entity_id == ref)
    ).first()

def scd2_update(
    db: Session,
    current_row: Event,
    *,
    changed_by: str,
    change_kind: str,
    **changes: Any,
) -> Event:
    """Close the current row's validity and insert a new version with
    the given changes. The old row is preserved unchanged except for
    valid_until. Caller commits."""
    now = datetime.now(UTC)
    new_row = Event(
        id=str(uuid7()),
        entity_id=current_row.entity_id,
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind=change_kind,
        **{f: getattr(current_row, f) for f in _MUTABLE_FIELDS},
        **changes,
    )
    current_row.valid_until = now
    db.add(new_row)
    db.flush()
    return new_row
```

`uuid7` is already a dep. The helper module stays under 100 lines.

## Mutation paths

| Route | Implementation |
|---|---|
| `POST /events` | New row: `id = uuid7()`, `entity_id = id` (self-ref), `valid_from = now`, `valid_until = NULL`, `changed_by = user.id`, `change_kind = "created"`. |
| `PUT /events/{id}` | Resolve via `current_event(db, id)`; call `scd2_update(... change_kind="updated", **changes)`. |
| `POST /events/{id}/archive` | `scd2_update(... change_kind="archived", archived_at=datetime.now(UTC))`. |
| `POST /events/{id}/restore` | `scd2_update(... change_kind="restored", archived_at=None)`. |

## Read paths

Every Event query gains a `valid_until IS NULL` filter (via the `current()` helper), unless it's specifically reading history (which we don't do anywhere in the app today).

| Route | After |
|---|---|
| `GET /events` | `current(query).filter(archived_at IS NULL)` |
| `GET /events/archived` | `current(query).filter(archived_at IS NOT NULL)` |
| `GET /events/by-slug/{slug}` | `current(query).filter(slug == slug, archived_at IS NULL)` |
| `GET /events/by-slug/{slug}/qr.png` | same |
| `GET /events/{id}/stats` | resolve via `current_event(db, id)`; signup join uses `entity_id` |
| `GET /events/{id}/feedback-summary` | resolve via `current_event`; response join uses `entity_id` |
| `POST /events/by-slug/{slug}/signups` | resolve via current; insert with `event_id = event.entity_id` |
| Feedback worker | `Signup.event_id == Event.entity_id` join; current Event filter |

## Slug uniqueness

`events.slug` currently has `unique=True`. Multiple versions share a slug, so:

```python
# Drop the table-level unique
# Add a partial unique that covers only the current version
op.create_index(
    "uq_events_slug_current",
    "events",
    ["slug"],
    unique=True,
    sqlite_where=sa.text("valid_until IS NULL"),
    postgresql_where=sa.text("valid_until IS NULL"),
)
```

SQLite + Postgres both support partial unique indexes. Drop the old `ix_events_slug` index and the column-level unique constraint at the same time.

## Alembic migration outline

Single migration, in order:

1. **Add the four new columns nullable, plus `change_kind`.**
   ```python
   op.add_column("events", sa.Column("entity_id", sa.Text, nullable=True))
   op.add_column("events", sa.Column("valid_from", sa.DateTime, nullable=True))
   op.add_column("events", sa.Column("valid_until", sa.DateTime, nullable=True))
   op.add_column("events", sa.Column("changed_by", sa.Text, nullable=True))
   op.add_column("events", sa.Column("change_kind", sa.Text, nullable=True))
   ```
2. **Backfill existing rows.** Each becomes its own first version.
   ```python
   op.execute("UPDATE events SET entity_id = id, "
              "valid_from = created_at, "
              "changed_by = created_by, "
              "change_kind = 'created'")
   ```
3. **Tighten constraints + add indexes.**
   ```python
   with op.batch_alter_table("events") as b:
       b.alter_column("entity_id", existing_type=sa.Text, nullable=False)
       b.alter_column("valid_from", existing_type=sa.DateTime, nullable=False)
       b.alter_column("changed_by", existing_type=sa.Text, nullable=False)
       b.alter_column("change_kind", existing_type=sa.Text, nullable=False)
       b.create_index("ix_events_entity_id", ["entity_id"])
       b.create_index("ix_events_valid_until", ["valid_until"])
       # FK on changed_by — explicit name so we can drop on Postgres
       b.create_foreign_key("fk_events_changed_by", "users", ["changed_by"], ["id"])
   ```
4. **Replace the slug unique with a partial unique on current versions.**
   - Drop `ix_events_slug` (the old column-level unique index).
   - Drop the column-level `unique=True` (via `alter_column`).
   - Create `uq_events_slug_current` partial unique.
5. **Drop the FK constraints on `signups.event_id`, `feedback_tokens.event_id`, `feedback_responses.event_id`.** (Per decision (a), no FK after the switch.)
6. **No data move on signups/tokens/responses.** Their `event_id` values are already the current row's id, which is also the `entity_id` after backfill (because every existing event's `entity_id = id` after step 2). The migration is a no-op for the data — just the constraint-shape changes.

The migration must work on both SQLite and Postgres. Per CLAUDE.md, use `op.get_context().dialect.name` if any constraint operation differs. Step 3's `batch_alter_table` is fine on SQLite; Postgres ignores `render_as_batch` for these ops.

## Pre-commit hook (`scd2-safety`)

Port from horeca-backend's `scripts/check_scd2_safety.py`. Flags:
- Any `db.query(Event)` not chained with `.filter(Event.valid_until.is_(None))` or `current(...)` or `current_event(...)`.
- Any `db.query(Event).filter(Event.id == X)` without the `valid_until` filter (callers should use `current_event` instead).
- Exempt with a `# scd2-history-ok: <reason>` comment for intentional history queries.

Wire into `lefthook.yml` (when we add lefthook to opkomst — currently absent; either ship it now or run the script via a separate `make` target). Suggested plan: ship a minimal `lefthook.yml` with `pre-commit: { commands: { scd2-safety: { run: python scripts/check_scd2_safety.py {staged_files} } } }` plus the existing `ruff` / `pyright` checks the repo doesn't yet run on commit.

## Test plan

End-to-end smoke test (extends the existing one):

1. Create event → 1 row total, `valid_until IS NULL`, `change_kind = "created"`, `entity_id = id`.
2. Edit name → 2 rows. Old: `valid_until` set, `name = old name`. New: `valid_until IS NULL`, `name = new name`, `change_kind = "updated"`, same `entity_id`.
3. Public `GET /e/{slug}` resolves to the new name.
4. Public `POST /events/by-slug/{slug}/signups` writes a Signup whose `event_id = event.entity_id` (not the new row's `id`).
5. Archive → 3 rows. Stats endpoint still aggregates over the entity (signup count from step 4 is included).
6. Restore → 4 rows. Public route serves again. Signup count unchanged.
7. Edit while archived: should it be allowed? **Decision: yes**, edits are independent of archive state. Test that editing an archived event creates a new "updated" version with `archived_at` still set (carried forward via `_MUTABLE_FIELDS`).
8. Migration on a populated dev DB: every existing event's first version has `change_kind = "created"`, `entity_id = id`, `valid_from = created_at`.

## Effort

| Step | Estimate |
|---|---|
| Schema + helpers | 30 min |
| Migration + backfill + slug uniqueness | 45 min |
| Router rewrites (8 sites) | 1 hour |
| Feedback worker join | 15 min |
| Drop FKs from signups / tokens / responses | 15 min |
| Pre-commit hook port + lefthook setup | 45 min |
| End-to-end smoke test + browser verify | 30 min |
| **Total** | **~4 hours** |

## Open questions for execution-time (none blocking)

- Whether to ship `lefthook.yml` in the same PR as the SCD2 work (recommend yes, since the hook depends on the helpers).
- Whether to display `change_kind` / `changed_by` anywhere in the UI. Per decision (3): no, but worth confirming when we touch it.
