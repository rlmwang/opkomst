"""The archive: a twin of every table that can hold an archived item.

An archived event is not a live event with a flag on it. It is data
nobody is working on, sitting in the tables every live query reads,
growing for ever — the ceilings in ``services/limits.py`` bound active
items, not finished ones. So archiving moves the rows out, into
``<table>_archive``, and the live tables hold only live data.

**The twins are generated, never written.** A hand-maintained mirror
rots the first time somebody adds a column and forgets its twin. Each
one here is derived from the live table at import time, so Alembic sees
both and a migration that adds a column emits the ``ALTER`` for the pair
from one definition. ``tests/test_archive_tables.py`` fails if a twin's
columns ever stop matching.

**They carry no foreign keys and no indexes.** An archived sign-up
points at an archived occurrence, and neither is in the table a key
would reference; referential integrity is enforced where rows are live,
which is where it matters, and a restore re-inserts into tables that
have it. Nothing reads a twin except a restore, which reads by the id it
already has, so an index would be storage spent on nothing.

The set of tables to mirror is the foreign-key graph, not a list: every
table that references an archivable root, transitively. A list would be
one more thing to forget. ``docs/design-archive-tables.md`` is the why.
"""

from collections import defaultdict, deque

from sqlalchemy import Column, MetaData, Table

from ..database import Base

# The four things an organiser archives. Everything else in the archive
# is there because it hangs off one of them.
ARCHIVABLE_ROOTS: tuple[str, ...] = ("events", "forms", "datepolls", "rosters")

# Its own MetaData, so ``Base.metadata`` stays the live schema and the
# twins cannot be picked up by anything that iterates the live tables
# (the tenancy audit, the seed, a naive "delete everything" in a test).
# Alembic is pointed at both.
archive_metadata = MetaData()


def _dependents() -> dict[str, set[str]]:
    """For each table, the tables holding a foreign key into it."""
    out: dict[str, set[str]] = defaultdict(set)
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            out[fk.column.table.name].add(table.name)
    return out


def dependent_tables(root: str) -> list[str]:
    """Every table that hangs off ``root``, nearest first.

    Breadth-first over the foreign-key graph, which is the same graph
    ``ON DELETE CASCADE`` follows — so what archiving moves and what
    deleting removes are the same set by construction, rather than by
    two lists somebody has to keep in step.

    Nearest-first is dependency order: parents come before the children
    that reference them, which is the order rows have to be written back
    in on a restore.
    """
    dependents = _dependents()
    seen: list[str] = []
    queue: deque[str] = deque([root])
    while queue:
        for child in sorted(dependents.get(queue.popleft(), ())):
            if child not in seen:
                seen.append(child)
                queue.append(child)
    return seen


def archived_tables() -> dict[str, list[str]]:
    """``{root: [root, *dependents]}`` for each archivable root."""
    return {root: [root, *dependent_tables(root)] for root in ARCHIVABLE_ROOTS}


def _mirror(live: Table) -> Table:
    """A copy of ``live``'s columns under ``<name>_archive``.

    Types and nullability travel; keys, indexes and server defaults do
    not. A server default would be wrong here — these rows are copied
    verbatim, never generated — and a key would point at a table the row
    has just left.
    """
    columns = [Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable) for c in live.columns]
    return Table(f"{live.name}_archive", archive_metadata, *columns)


def archive_name(table: str) -> str:
    return f"{table}_archive"


# Built once, at import: every table any root can reach, plus the roots.
MIRRORED: tuple[str, ...] = tuple(dict.fromkeys(name for names in archived_tables().values() for name in names))

for _name in MIRRORED:
    _mirror(Base.metadata.tables[_name])
