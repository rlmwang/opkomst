"""Moving an item, and everything under it, in and out of the archive.

Archiving used to be a column. It is a move now: the rows leave the live
tables for their twins in ``models/archive.py``, so the tables every
live query reads hold only live data and the archive grows on its own.

Three operations, each walking the same foreign-key graph:

* ``archive`` — copy the graph into the twins, then delete it from the
  live tables. Children first on the way out, so no live row is ever
  left pointing at a parent that has gone.
* ``restore`` — the reverse, parents first, then delete from the twins.
  Ids are preserved, so the public link and every edit link a visitor
  saved still work: a restored event is the same event.
* ``purge`` — delete from the twins and never write the rows back.

Each is one transaction. A crash mid-archive rolls back to an item that
is entirely live, which is the state everything else already knows how
to handle.

The graph is derived, not listed (``models/archive.py::dependent_tables``).
The row sets are found by walking down from the root one table at a
time: every table names its parent, so "the signups of these
occurrences" is a plain ``IN``, and no query needs to know the shape of
the graph above it.
"""

import structlog
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..database import Base
from ..models.archive import ARCHIVABLE_ROOTS, archive_metadata, dependent_tables

logger = structlog.get_logger()


def _parent_columns(table: str, known: set[str]) -> list[tuple[str, str]]:
    """``(column, parent_table)`` for each foreign key of ``table`` that
    points at a table already in the set being moved.

    A table can reference things outside the move — ``tenant_id``,
    ``created_by``, ``chapter_id`` — and those are not what selects its
    rows. What selects them is the key that points at the parent we are
    moving.
    """
    live = Base.metadata.tables[table]
    return [(fk.parent.name, fk.column.table.name) for fk in live.foreign_keys if fk.column.table.name in known]


def _row_ids(db: Session, root: str, root_id: str) -> dict[str, list[str]]:
    """The id of every row being moved, per table, in dependency order.

    Walks down from the root: each table's rows are the ones whose
    foreign key names an id already collected for its parent. A table
    with two keys into the set (a shift naming both a chore and a
    volunteer) matches on either, because either is a reason for the row
    to travel with the item.
    """
    found: dict[str, list[str]] = {root: [root_id]}
    for table in dependent_tables(root):
        parents = _parent_columns(table, set(found))
        if not parents:
            continue
        live = Base.metadata.tables[table]
        clauses = [live.c[column].in_(found[parent]) for column, parent in parents if found[parent]]
        if not clauses:
            found[table] = []
            continue
        condition = clauses[0]
        for extra in clauses[1:]:
            condition = condition | extra
        found[table] = [row[0] for row in db.execute(select(live.c.id).where(condition))]
    return found


def _move(db: Session, tables: list[str], ids: dict[str, list[str]], *, to_archive: bool) -> int:
    """Copy rows between a table and its twin, then delete the source.

    ``INSERT INTO … SELECT`` keeps the rows in the database: nothing is
    read into Python, so the cost does not grow with how much an event
    collected. Writes go parents-first and deletes children-first, which
    is the only ordering that never leaves a row pointing at a parent
    that is not there.
    """
    moved = 0
    for table in tables:
        row_ids = ids.get(table) or []
        if not row_ids:
            continue
        live = Base.metadata.tables[table]
        twin = archive_metadata.tables[f"{table}_archive"]
        source, target = (live, twin) if to_archive else (twin, live)
        columns = [c.name for c in live.columns]
        db.execute(
            insert(target).from_select(
                columns, select(*[source.c[name] for name in columns]).where(source.c.id.in_(row_ids))
            )
        )
        moved += len(row_ids)
    for table in reversed(tables):
        row_ids = ids.get(table) or []
        if not row_ids:
            continue
        live = Base.metadata.tables[table]
        twin = archive_metadata.tables[f"{table}_archive"]
        source = live if to_archive else twin
        db.execute(delete(source).where(source.c.id.in_(row_ids)))
    return moved


def _archived_row_ids(db: Session, root: str, root_id: str) -> dict[str, list[str]]:
    """The same walk, over the twins: what is in the archive for an item."""
    found: dict[str, list[str]] = {root: [root_id]}
    for table in dependent_tables(root):
        parents = _parent_columns(table, set(found))
        if not parents:
            continue
        twin = archive_metadata.tables[f"{table}_archive"]
        clauses = [twin.c[column].in_(found[parent]) for column, parent in parents if found[parent]]
        if not clauses:
            found[table] = []
            continue
        condition = clauses[0]
        for extra in clauses[1:]:
            condition = condition | extra
        found[table] = [row[0] for row in db.execute(select(twin.c.id).where(condition))]
    return found


def archive_item(db: Session, root: str, root_id: str) -> int:
    """Move an item and everything under it into the archive. Returns the
    number of rows moved. Does not commit: the caller owns the
    transaction, so the move and whatever else it does are one."""
    _assert_root(root)
    ids = _row_ids(db, root, root_id)
    tables = [root, *dependent_tables(root)]
    moved = _move(db, tables, ids, to_archive=True)
    # The rows moved out from under any ORM object the caller is holding.
    # Expiring says so, rather than letting the next attribute read raise
    # ObjectDeletedError somewhere unrelated.
    db.expire_all()
    logger.info("archive_moved", root=root, entity_id=root_id, rows=moved)
    return moved


def restore_item(db: Session, root: str, root_id: str) -> int:
    """Move an item back out of the archive, ids intact."""
    _assert_root(root)
    ids = _archived_row_ids(db, root, root_id)
    tables = [root, *dependent_tables(root)]
    moved = _move(db, tables, ids, to_archive=False)
    db.expire_all()
    logger.info("archive_restored", root=root, entity_id=root_id, rows=moved)
    return moved


def purge_item(db: Session, root: str, root_id: str) -> int:
    """Delete an archived item outright. The twins have no cascades, so
    this walks the same graph and deletes children first."""
    _assert_root(root)
    ids = _archived_row_ids(db, root, root_id)
    removed = 0
    for table in reversed([root, *dependent_tables(root)]):
        row_ids = ids.get(table) or []
        if not row_ids:
            continue
        twin = archive_metadata.tables[f"{table}_archive"]
        db.execute(delete(twin).where(twin.c.id.in_(row_ids)))
        removed += len(row_ids)
    db.expire_all()
    logger.info("archive_purged", root=root, entity_id=root_id, rows=removed)
    return removed


def _assert_root(root: str) -> None:
    if root not in ARCHIVABLE_ROOTS:
        raise ValueError(f"{root} is not an archivable root")


__all__ = ["archive_item", "purge_item", "restore_item"]


# Kept out of the public names above: only the tests and a future
# admin surface have a reason to ask.
def archived_ids(db: Session, root: str) -> list[str]:
    """Every archived item's id for one root, newest first."""
    _assert_root(root)
    twin = archive_metadata.tables[f"{root}_archive"]
    order = twin.c.archived_at.desc() if "archived_at" in twin.c else twin.c.id.desc()
    return [row[0] for row in db.execute(select(twin.c.id).order_by(order))]
