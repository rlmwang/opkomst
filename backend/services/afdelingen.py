"""Afdeling SCD2 helpers + business logic.

The afdelingen table is strict SCD2:
- The current version is the row with ``valid_until IS NULL``.
- Updates close the old row (set its ``valid_until``) and insert a
  new one with the same ``entity_id``.
- Soft-delete sets ``valid_until`` on the current row, no replacement.
- Restore inserts a new row with ``valid_until = NULL`` and the same
  ``entity_id``, change_kind="restored".

External references (Event.afdeling_id, User.afdeling_id) point at
``entity_id``, so they survive every state change.
"""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Query, Session
from uuid_utils import uuid7

from ..models import Afdeling


def current(query: "Query[Afdeling]") -> "Query[Afdeling]":
    """Restrict an afdeling query to the current version of each entity."""
    return query.filter(Afdeling.valid_until.is_(None))


def all_active(db: Session) -> list[Afdeling]:
    return current(db.query(Afdeling)).order_by(Afdeling.name).all()


def latest_versions(db: Session, *, include_archived: bool) -> list[Afdeling]:
    """One row per ``entity_id``: the current version if there is
    one, otherwise the most recently archived version. Used by the
    autocomplete on the admin page so soft-deleted afdelingen surface
    for restore."""
    if not include_archived:
        return all_active(db)
    # Group by entity_id; pick max(valid_from) per group. SQLite supports
    # the row-number trick via a subquery.
    sub = (
        db.query(Afdeling.entity_id, Afdeling.valid_from)
        .order_by(Afdeling.entity_id, Afdeling.valid_from.desc())
        .all()
    )
    seen: set[str] = set()
    keep_pairs: list[tuple[str, datetime]] = []
    for entity_id, valid_from in sub:
        if entity_id in seen:
            continue
        seen.add(entity_id)
        keep_pairs.append((entity_id, valid_from))
    if not keep_pairs:
        return []
    keep_keys = {(eid, vf) for eid, vf in keep_pairs}
    rows = db.query(Afdeling).all()
    latest = [a for a in rows if (a.entity_id, a.valid_from) in keep_keys]
    return sorted(latest, key=lambda a: a.name.lower())


def find_current_by_entity(db: Session, entity_id: str) -> Afdeling | None:
    return current(db.query(Afdeling)).filter(Afdeling.entity_id == entity_id).first()


def find_any_by_entity(db: Session, entity_id: str) -> Afdeling | None:
    """Latest version (current or archived) for a given entity_id."""
    return (
        db.query(Afdeling)
        .filter(Afdeling.entity_id == entity_id)
        .order_by(Afdeling.valid_from.desc())
        .first()
    )


def is_archived(db: Session, entity_id: str) -> bool:
    return find_current_by_entity(db, entity_id) is None and find_any_by_entity(db, entity_id) is not None


def normalise_name(name: str) -> str:
    """Strip surrounding whitespace + collapse internal runs to a
    single space. ``" Den   Haag  "`` → ``"Den Haag"``. Applied
    uniformly on every write and every case-insensitive match so
    duplicate detection isn't fooled by trailing or doubled spaces."""
    return " ".join(name.split())


def name_for_entity(db: Session, entity_id: str | None) -> str | None:
    """Resolve an entity_id to a display name. Falls back to the most
    recent archived version when the current one is gone (so users
    assigned to a since-deleted afdeling still render readably)."""
    if entity_id is None:
        return None
    row = find_current_by_entity(db, entity_id) or find_any_by_entity(db, entity_id)
    return row.name if row else None


def name_exists_active(db: Session, name: str, *, exclude_entity_id: str | None = None) -> bool:
    """True if an active afdeling already has this name (whitespace-
    normalised + case-insensitive). The optional ``exclude_entity_id``
    lets the rename flow skip its own row."""
    needle = normalise_name(name).lower()
    q = current(db.query(Afdeling)).filter(func.lower(Afdeling.name) == needle)
    if exclude_entity_id is not None:
        q = q.filter(Afdeling.entity_id != exclude_entity_id)
    return q.first() is not None


def create(db: Session, *, name: str, changed_by: str) -> Afdeling:
    name = normalise_name(name)
    now = datetime.now(UTC)
    new_id = str(uuid7())
    row = Afdeling(
        id=new_id,
        name=name,
        entity_id=new_id,  # first version self-references
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind="created",
    )
    db.add(row)
    db.flush()
    return row


def rename(db: Session, *, entity_id: str, name: str, changed_by: str) -> Afdeling | None:
    """SCD2 update: close the current version, insert a new one with
    the new name. Same entity_id, so every row in events / users
    pointing at this chapter follows the rename automatically.

    Refuses with ValueError when the new name collides (case-
    insensitive) with another active chapter.
    """
    name = normalise_name(name)
    current_row = find_current_by_entity(db, entity_id)
    if current_row is None:
        return None
    if name_exists_active(db, name, exclude_entity_id=entity_id):
        raise ValueError("Name already in use")
    now = datetime.now(UTC)
    new_row = Afdeling(
        id=str(uuid7()),
        name=name,
        entity_id=entity_id,
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind="updated",
    )
    current_row.valid_until = now
    db.add(new_row)
    db.flush()
    return new_row


def archive(db: Session, *, entity_id: str, changed_by: str) -> Afdeling | None:
    """Soft-delete: set valid_until on the current version, no
    replacement row. Returns the closed row, or None if there was no
    current version to close."""
    current_row = find_current_by_entity(db, entity_id)
    if current_row is None:
        return None
    now = datetime.now(UTC)
    current_row.valid_until = now
    # Mark this final closing edit so audit log readers see what
    # happened. We rewrite change_kind on the closed row rather than
    # creating a separate "tombstone" — the SCD2 timeline is still
    # readable: the row's last action was the archive.
    current_row.change_kind = "archived"
    current_row.changed_by = changed_by
    db.add(current_row)
    db.flush()
    return current_row


def restore(db: Session, *, entity_id: str, changed_by: str) -> Afdeling:
    """Insert a new current version for a previously-archived entity.
    Copies the most recent name forward; the admin can rename via a
    separate update.

    Refuses if the archived name now collides (case-insensitive) with
    another active chapter — this prevents the "delete X → create new
    X → restore old X" duplicate-name footgun.
    """
    last = find_any_by_entity(db, entity_id)
    if last is None:
        raise ValueError(f"No afdeling history for entity_id={entity_id}")
    if last.valid_until is None:
        raise ValueError("Afdeling is already current")
    if name_exists_active(db, last.name):
        raise ValueError(
            f"Name '{last.name}' is already in use by another chapter — "
            "rename or delete that one first."
        )
    now = datetime.now(UTC)
    new_row = Afdeling(
        id=str(uuid7()),
        name=last.name,
        entity_id=entity_id,
        valid_from=now,
        valid_until=None,
        changed_by=changed_by,
        change_kind="restored",
    )
    db.add(new_row)
    db.flush()
    return new_row
