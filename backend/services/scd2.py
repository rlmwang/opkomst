"""Generic SCD2 helpers for every dimension table that mixes in
``SCD2Mixin``. Used by Event, Chapter, and User — adding a new SCD2
table is one mixin + a model definition, no per-table boilerplate.

A logical entity is a chain of rows sharing one ``entity_id``. The
current row has ``valid_until IS NULL``; every other row is history.
The row id changes on every edit; ``entity_id`` is stable. Public
DTOs always expose ``entity_id`` as ``id`` — clients never see a
per-version row id.

Two write shapes:

* ``scd2_update`` — close the current row, insert a new row with the
  same ``entity_id`` and the requested changes. Used for edits and
  for state transitions that should be visible in the timeline
  (Event archive / restore).
* ``scd2_close`` — stamp ``valid_until`` on the current row, no
  replacement row. Used when the SCD2 chain itself is being shut
  down (Chapter delete) — restore mints a new row in a separate
  step.

Reads always go through ``current(...)`` so history rows never leak
into business logic. The ``scd2-safety`` pre-commit hook (port from
horeca-backend) catches any bare ``db.query(<SCD2Model>)`` that
forgets the filter.
"""

from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy.orm import Query, Session
from uuid_utils import uuid7

from ..mixins import SCD2Mixin

T = TypeVar("T", bound=SCD2Mixin)

# Columns the SCD2 machinery owns — they don't carry forward when a
# new version is minted.
_SCD2_OWNED = frozenset(
    {
        "id",
        "entity_id",
        "valid_from",
        "valid_until",
        "changed_by",
        "change_kind",
        "created_at",
        "updated_at",
    }
)


def _model_of(query: "Query[Any]") -> type:
    """The first mapped entity in a query."""
    return query.column_descriptions[0]["entity"]


def current(query: "Query[T]") -> "Query[T]":
    """Restrict an SCD2 query to current-version rows only."""
    model = _model_of(query)
    return query.filter(model.valid_until.is_(None))


def current_by_entity(db: Session, model: type[T], entity_id: str) -> T | None:
    """Resolve an entity_id to its current row, or None."""
    return (
        db.query(model)
        .filter(model.entity_id == entity_id, model.valid_until.is_(None))
        .first()
    )


def latest_by_entity(db: Session, model: type[T], entity_id: str) -> T | None:
    """Latest row for an entity_id (current or most-recently-archived).
    For surfaces that need to render a name even when the chain is
    closed (e.g. resolving a chapter_id on a still-living user
    after the chapter was deleted)."""
    return (
        db.query(model)
        .filter(model.entity_id == entity_id)
        .order_by(model.valid_from.desc())
        .first()
    )


def _carry_forward_fields(model: type) -> list[str]:
    """Mapped columns that copy across versions: every column except
    the SCD2-managed set."""
    return [c.name for c in model.__table__.columns if c.name not in _SCD2_OWNED]


def scd2_create(
    db: Session,
    model: type[T],
    *,
    changed_by: str,
    **fields: Any,
) -> T:
    """Insert a brand-new SCD2 chain. ``entity_id`` self-references
    on the first row; subsequent versions inherit it via
    ``scd2_update``."""
    new_id = str(uuid7())
    now = datetime.now(UTC)
    row = model(
        id=new_id,
        entity_id=new_id,
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind="created",
        **fields,
    )
    db.add(row)
    db.flush()
    return row


def scd2_update(
    db: Session,
    current_row: T,
    *,
    changed_by: str,
    change_kind: str = "updated",
    **changes: Any,
) -> T:
    """Close the current row and insert a new version with the
    requested changes. Caller commits."""
    model = type(current_row)
    forwarded = {f: getattr(current_row, f) for f in _carry_forward_fields(model)}
    forwarded.update(changes)
    now = datetime.now(UTC)
    new_row = model(
        id=str(uuid7()),
        entity_id=current_row.entity_id,
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind=change_kind,
        **forwarded,
    )
    current_row.valid_until = now
    db.add(new_row)
    db.flush()
    return new_row


def scd2_close(
    db: Session,
    current_row: T,
    *,
    changed_by: str,
    change_kind: str = "archived",
) -> T:
    """Stamp ``valid_until`` on the current row, no replacement.
    Use for chain shutdowns where the entity itself is going away
    (Chapter delete). Restore mints a brand new current row in a
    separate step. Caller commits."""
    now = datetime.now(UTC)
    current_row.valid_until = now
    current_row.changed_by = changed_by
    current_row.change_kind = change_kind
    db.add(current_row)
    db.flush()
    return current_row


def scd2_restore(
    db: Session,
    last_row: T,
    *,
    changed_by: str,
) -> T:
    """Insert a fresh current row for a previously-closed chain.
    ``last_row`` is the most recently archived version (the row whose
    state the restore copies forward). Caller commits."""
    model = type(last_row)
    forwarded = {f: getattr(last_row, f) for f in _carry_forward_fields(model)}
    now = datetime.now(UTC)
    new_row = model(
        id=str(uuid7()),
        entity_id=last_row.entity_id,
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind="restored",
        **forwarded,
    )
    db.add(new_row)
    db.flush()
    return new_row
