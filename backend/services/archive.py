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

from typing import Any

import structlog
from sqlalchemy import delete, false, func, insert, select
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


def _selection(db: Session, root: str, root_id: str, *, archived: bool) -> dict[str, Any]:
    """A WHERE clause per table, selecting the rows that belong to one
    item, in dependency order.

    Walks down from the root: a table's rows are the ones whose foreign
    key names a row already selected from its parent. A table with two
    keys into the set — a shift naming both a chore and a volunteer — is
    selected by either, because either is a reason to travel with the
    item.

    Ids are collected only for the tables that have one, and only
    because their children need them. ``enrollments`` is a join table
    with a composite key and no ``id`` at all; nothing references it, so
    nothing ever asks.
    """

    def table_of(name: str) -> Any:
        live = Base.metadata.tables[name]
        return archive_metadata.tables[f"{name}_archive"] if archived else live

    root_table = table_of(root)
    conditions: dict[str, Any] = {root: root_table.c.id == root_id}
    ids: dict[str, list[str]] = {root: [root_id]}

    for name in dependent_tables(root):
        table = table_of(name)
        parents = _parent_columns(name, set(conditions))
        clauses = [table.c[column].in_(ids[parent]) for column, parent in parents if ids.get(parent)]
        if not clauses:
            # Every parent came back empty, so this table has nothing to
            # move either. ``false()`` keeps the shape without a query.
            conditions[name] = false()
            if "id" in table.c:
                ids[name] = []
            continue
        condition = clauses[0]
        for extra in clauses[1:]:
            condition = condition | extra
        conditions[name] = condition
        if "id" in table.c:
            ids[name] = [row[0] for row in db.execute(select(table.c.id).where(condition))]
    return conditions


def _move(db: Session, root: str, conditions: dict[str, Any], *, to_archive: bool) -> int:
    """Copy each table's selected rows to its twin, then delete them.

    ``INSERT INTO … SELECT`` keeps the rows in the database: nothing is
    read into Python, so the cost does not grow with how much an event
    collected. Writes go parents-first and deletes children-first, the
    only ordering that never leaves a row pointing at a parent that has
    gone.
    """
    tables = [root, *dependent_tables(root)]
    moved = 0
    for name in tables:
        live = Base.metadata.tables[name]
        twin = archive_metadata.tables[f"{name}_archive"]
        source, target = (live, twin) if to_archive else (twin, live)
        columns = [c.name for c in live.columns]
        result = db.execute(
            insert(target).from_select(columns, select(*[source.c[c] for c in columns]).where(conditions[name]))
        )
        moved += getattr(result, "rowcount", 0) or 0
    for name in reversed(tables):
        live = Base.metadata.tables[name]
        twin = archive_metadata.tables[f"{name}_archive"]
        source = live if to_archive else twin
        db.execute(delete(source).where(conditions[name]))
    return moved


def archive_item(db: Session, root: str, root_id: str) -> int:
    """Move an item and everything under it into the archive. Returns the
    number of rows moved. Does not commit: the caller owns the
    transaction, so the move and whatever else it does are one."""
    _assert_root(root)
    conditions = _selection(db, root, root_id, archived=False)
    moved = _move(db, root, conditions, to_archive=True)
    # The rows moved out from under any ORM object the caller is holding.
    # Expiring says so, rather than letting the next attribute read raise
    # ObjectDeletedError somewhere unrelated.
    db.expire_all()
    logger.info("archive_moved", root=root, entity_id=root_id, rows=moved)
    return moved


def restore_item(db: Session, root: str, root_id: str) -> int:
    """Move an item back out of the archive, ids intact."""
    _assert_root(root)
    conditions = _selection(db, root, root_id, archived=True)
    moved = _move(db, root, conditions, to_archive=False)
    db.expire_all()
    logger.info("archive_restored", root=root, entity_id=root_id, rows=moved)
    return moved


def purge_item(db: Session, root: str, root_id: str) -> int:
    """Delete an archived item outright. The twins have no cascades, so
    this walks the same graph and deletes children first."""
    _assert_root(root)
    conditions = _selection(db, root, root_id, archived=True)
    removed = 0
    for name in reversed([root, *dependent_tables(root)]):
        twin = archive_metadata.tables[f"{name}_archive"]
        result = db.execute(delete(twin).where(conditions[name]))
        removed += getattr(result, "rowcount", 0) or 0
    db.expire_all()
    logger.info("archive_purged", root=root, entity_id=root_id, rows=removed)
    return removed


def find_one(db: Session, table: str, column: str, value: Any) -> Any:
    """One archived row by any column, or ``None``.

    The public read paths use this when the live tables come up empty:
    an item that was archived is Gone rather than never-existed, and a
    feedback link emailed before the archive still has to work.
    """
    twin = archive_metadata.tables[f"{table}_archive"]
    return db.execute(select(twin).where(twin.c[column] == value)).mappings().first()


def add_row(db: Session, table: str, values: dict[str, Any]) -> None:
    """Write a row straight into an archive twin.

    The one write the archive takes that is not a move: a feedback
    response submitted against an event that was archived while the
    email sat in somebody's inbox. It belongs with the occurrence it
    answers, and that occurrence is here."""
    twin = archive_metadata.tables[f"{table}_archive"]
    db.execute(insert(twin).values(**values))


def delete_row(db: Session, table: str, column: str, value: Any) -> None:
    """Delete archived rows by any column. Used to burn a feedback token
    that has been redeemed, wherever it lives."""
    twin = archive_metadata.tables[f"{table}_archive"]
    db.execute(delete(twin).where(twin.c[column] == value))


def child_counts(db: Session, table: str, column: str, parent_ids: list[str]) -> dict[str, int]:
    """``parent_id -> COUNT(*)`` over an archive twin.

    The list pages show how many chores a roster had, how many people
    came. Those children are in the archive too, so the counts have to be
    read there — the live table is empty of them by design."""
    if not parent_ids:
        return {}
    twin = archive_metadata.tables[f"{table}_archive"]
    rows = db.execute(
        select(twin.c[column], func.count()).where(twin.c[column].in_(parent_ids)).group_by(twin.c[column])
    )
    return {parent_id: int(count) for parent_id, count in rows}


def child_sums(db: Session, table: str, column: str, value: str, parent_ids: list[str]) -> dict[str, int]:
    """``parent_id -> SUM(value)`` over an archive twin, for the counts
    that add something up rather than count rows — a headcount is the
    sum of party sizes, not the number of bookings."""
    if not parent_ids:
        return {}
    twin = archive_metadata.tables[f"{table}_archive"]
    rows = db.execute(
        select(twin.c[column], func.coalesce(func.sum(twin.c[value]), 0))
        .where(twin.c[column].in_(parent_ids))
        .group_by(twin.c[column])
    )
    return {parent_id: int(total or 0) for parent_id, total in rows}


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
