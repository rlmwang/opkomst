"""The archive twins match the tables they mirror.

``backend/models/archive.py`` generates one ``<table>_archive`` per live
table an archived item can reach. Generation is what stops the two
drifting, so these tests guard the generation: the set of mirrored
tables, the columns in each twin, and the absence of the keys and
indexes a twin must not have.

A twin that has fallen behind its live table is a restore that fails
years later, in front of the person who wanted their event back. It
should be a failing test today instead.
"""

from sqlalchemy import inspect

from backend.database import Base, engine
from backend.models.archive import (
    ARCHIVABLE_ROOTS,
    MIRRORED,
    NEVER_ARCHIVED,
    archive_metadata,
    archived_tables,
    dependent_tables,
)


def test_every_mirrored_table_has_a_twin_with_the_same_columns() -> None:
    for name in MIRRORED:
        live = Base.metadata.tables[name]
        twin = archive_metadata.tables[f"{name}_archive"]
        assert [c.name for c in twin.columns] == [c.name for c in live.columns], name
        for column in live.columns:
            assert str(twin.columns[column.name].type) == str(column.type), f"{name}.{column.name}"
            assert twin.columns[column.name].nullable == column.nullable, f"{name}.{column.name}"


def test_twins_carry_no_keys_and_no_indexes() -> None:
    """An archived row points at a world it has left: the occurrence its
    foreign key names is in the archive too. Integrity is enforced where
    rows are live, and a restore writes back into the tables that have
    it."""
    for name in MIRRORED:
        twin = archive_metadata.tables[f"{name}_archive"]
        assert not twin.foreign_keys, name
        assert not twin.indexes, name


def test_the_mirrored_set_is_the_foreign_key_graph() -> None:
    """Not a list somebody maintains. Every table reachable from an
    archivable root, and nothing else."""
    graph = archived_tables()
    assert set(graph) == set(ARCHIVABLE_ROOTS)
    assert set(MIRRORED) == {name for names in graph.values() for name in names}

    # The shape at the time of writing, so a model change that adds or
    # drops a dependent table is visible in a diff rather than silent.
    assert graph["events"] == [
        "events",
        "occurrences",
        "registrations",
        "email_send_counts",
        "feedback_responses",
        "feedback_tokens",
        "signups",
    ]
    assert graph["forms"] == ["forms", "compass_axes", "form_questions", "form_responses", "form_submissions"]
    assert graph["datepolls"] == ["datepolls", "datepoll_slots", "datepoll_submissions", "datepoll_responses"]


def test_email_dispatches_never_travels_and_has_no_twin() -> None:
    """A dispatch row is an email still owed, and the only place an
    attendee's address lives. Archiving says that email is never going
    to be sent, so the row is deleted and counted failed at the move
    (``services/archive.py::_discard_dispatches``). Nothing sweeps the
    archive, so a twin here would hold the ciphertext for ever."""
    assert "email_dispatches" in NEVER_ARCHIVED
    assert "email_dispatches" not in MIRRORED
    assert all("email_dispatches" not in names for names in archived_tables().values())
    assert "email_dispatches_archive" not in archive_metadata.tables


def test_dependents_come_after_the_tables_they_reference() -> None:
    """Nearest-first is dependency order, which is the order a restore
    has to write rows back in: a signup cannot be inserted before the
    occurrence it names."""
    order = dependent_tables("events")
    assert order.index("occurrences") < order.index("signups")
    assert order.index("registrations") < order.index("signups")
    assert order.index("occurrences") < order.index("feedback_tokens")


def test_the_twins_exist_in_the_database() -> None:
    """The migration created them, and it created all of them."""
    tables = set(inspect(engine).get_table_names())
    for name in MIRRORED:
        assert f"{name}_archive" in tables, name


def test_no_twin_is_in_the_live_metadata() -> None:
    """The archive has its own ``MetaData`` so anything that walks the
    live schema — the tenancy audit, the seed, a test that truncates
    everything — cannot pick up an archive table by accident."""
    for name in Base.metadata.tables:
        assert not name.endswith("_archive"), name
