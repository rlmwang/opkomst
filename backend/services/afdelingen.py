"""Afdeling business logic on top of the generic SCD2 helpers in
``services.scd2``. The CRUD primitives (open chain, mint version,
close, restore) live in the shared module; this file only carries
afdeling-specific concerns: name normalisation, dupe checks, and
the restore-collision rule."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Afdeling
from . import scd2


def normalise_name(name: str) -> str:
    """Strip surrounding whitespace + collapse internal runs to a
    single space. ``" Den   Haag  "`` → ``"Den Haag"``. Applied
    uniformly on every write and every case-insensitive match so
    duplicate detection isn't fooled by trailing or doubled spaces."""
    return " ".join(name.split())


def all_active(db: Session) -> list[Afdeling]:
    return scd2.current(db.query(Afdeling)).order_by(Afdeling.name).all()


def latest_versions(db: Session, *, include_archived: bool) -> list[Afdeling]:
    """One row per ``entity_id``: the current version if there is one,
    otherwise the most recently archived. Used by the admin
    autocomplete so deleted afdelingen surface for restore."""
    if not include_archived:
        return all_active(db)
    seen: set[str] = set()
    keep: list[tuple[str, "object"]] = []
    sub = (
        db.query(Afdeling.entity_id, Afdeling.valid_from)
        .order_by(Afdeling.entity_id, Afdeling.valid_from.desc())
        .all()
    )
    for entity_id, valid_from in sub:
        if entity_id in seen:
            continue
        seen.add(entity_id)
        keep.append((entity_id, valid_from))
    if not keep:
        return []
    keys = set(keep)
    rows = db.query(Afdeling).all()  # scd2-history-ok: deliberate scan over full chain
    latest = [a for a in rows if (a.entity_id, a.valid_from) in keys]
    return sorted(latest, key=lambda a: a.name.lower())


def find_current_by_entity(db: Session, entity_id: str) -> Afdeling | None:
    return scd2.current_by_entity(db, Afdeling, entity_id)


def find_any_by_entity(db: Session, entity_id: str) -> Afdeling | None:
    return scd2.latest_by_entity(db, Afdeling, entity_id)


def is_archived(db: Session, entity_id: str) -> bool:
    return find_current_by_entity(db, entity_id) is None and find_any_by_entity(db, entity_id) is not None


def name_for_entity(db: Session, entity_id: str | None) -> str | None:
    """Resolve an entity_id to a display name, falling back to the
    most recent archived version when the chain is closed."""
    if entity_id is None:
        return None
    row = find_current_by_entity(db, entity_id) or find_any_by_entity(db, entity_id)
    return row.name if row else None


def name_exists_active(db: Session, name: str, *, exclude_entity_id: str | None = None) -> bool:
    needle = normalise_name(name).lower()
    q = scd2.current(db.query(Afdeling)).filter(func.lower(Afdeling.name) == needle)
    if exclude_entity_id is not None:
        q = q.filter(Afdeling.entity_id != exclude_entity_id)
    return q.first() is not None


def create(db: Session, *, name: str, changed_by: str) -> Afdeling:
    return scd2.scd2_create(db, Afdeling, changed_by=changed_by, name=normalise_name(name))


def rename(db: Session, *, entity_id: str, name: str, changed_by: str) -> Afdeling | None:
    name = normalise_name(name)
    current_row = find_current_by_entity(db, entity_id)
    if current_row is None:
        return None
    if name_exists_active(db, name, exclude_entity_id=entity_id):
        raise ValueError("Name already in use")
    return scd2.scd2_update(db, current_row, changed_by=changed_by, name=name)


def update(
    db: Session,
    *,
    entity_id: str,
    changed_by: str,
    name: str | None = None,
    city: str | None = None,
    city_lat: float | None = None,
    city_lon: float | None = None,
    set_city: bool = False,
) -> Afdeling | None:
    """Generic SCD2 update for an afdeling. Pass only the fields that
    should change; ``set_city=True`` is required to actually write
    the city tuple (which can be ``None``/``None``/``None`` to clear
    a previously-set city). Without ``set_city``, a missing city
    payload doesn't accidentally overwrite an existing city to NULL."""
    current_row = find_current_by_entity(db, entity_id)
    if current_row is None:
        return None
    changes: dict[str, object] = {}
    if name is not None:
        name = normalise_name(name)
        if name != current_row.name:
            if name_exists_active(db, name, exclude_entity_id=entity_id):
                raise ValueError("Name already in use")
            changes["name"] = name
    if set_city:
        changes["city"] = city
        changes["city_lat"] = city_lat
        changes["city_lon"] = city_lon
    if not changes:
        return current_row
    return scd2.scd2_update(db, current_row, changed_by=changed_by, **changes)


def archive(db: Session, *, entity_id: str, changed_by: str) -> Afdeling | None:
    """Soft-delete: stamp ``valid_until`` on the current row, no
    replacement. Restore is a separate flow."""
    current_row = find_current_by_entity(db, entity_id)
    if current_row is None:
        return None
    return scd2.scd2_close(db, current_row, changed_by=changed_by, change_kind="archived")


def restore(db: Session, *, entity_id: str, changed_by: str) -> Afdeling:
    """Insert a new current row for a previously-archived entity.
    Refuses if the archived name now collides (case-insensitive)
    with another active chapter — prevents the
    "delete X → create new X → restore old X" duplicate-name
    footgun."""
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
    return scd2.scd2_restore(db, last, changed_by=changed_by)
