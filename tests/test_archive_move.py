"""Archiving moves rows out; restoring puts them back exactly.

The contract these prove:

* after an archive, the live tables hold nothing of the item and the
  twins hold all of it;
* after a restore, every row is back, byte for byte, under the same id —
  which is what keeps a visitor's saved edit link working;
* a purge leaves nothing anywhere;
* one item's archive does not touch another's rows.

``services/archive.py`` derives what to move from the foreign-key graph,
so a new child table is covered by these tests the day it is added,
without anyone remembering to extend them.
"""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import first_occurrence, make_event
from _helpers.signups import make_signup
from sqlalchemy import func, select

from backend.database import Base
from backend.models import Occurrence, Registration, Signup
from backend.models.archive import archive_metadata, dependent_tables
from backend.services import archive


def _live_count(db: Any, table: str) -> int:
    t = Base.metadata.tables[table]
    return db.execute(select(func.count()).select_from(t)).scalar() or 0


def _archived_count(db: Any, table: str) -> int:
    t = archive_metadata.tables[f"{table}_archive"]
    return db.execute(select(func.count()).select_from(t)).scalar() or 0


def _snapshot(db: Any, table: str) -> list[tuple]:
    """Every row of a live table, ordered, as plain tuples."""
    t = Base.metadata.tables[table]
    return [tuple(r) for r in db.execute(select(t).order_by(t.c.id))]


def _event_with_everything(db: Any) -> Any:
    """An event carrying the whole graph: occurrences, a registration,
    a signup, and a pending dispatch."""
    event = make_event(db, starts_in=timedelta(days=3), feedback_enabled=True, reminder_enabled=True)
    make_signup(db, event, email="alice@example.test")
    commit(db)
    return event


def test_archiving_empties_the_live_tables_and_fills_the_twins(db: Any) -> None:
    event = _event_with_everything(db)
    tables = ["events", *dependent_tables("events")]
    before = {t: _live_count(db, t) for t in tables}
    assert before["signups"] == 1 and before["occurrences"] >= 1
    # Counted before the move, because the move is what turns each of
    # them into a failed tally.
    # One per channel: the reminder and the feedback mail.
    owed = _live_count(db, "email_dispatches")
    assert owed == 2

    archive.archive_item(db, "events", event.id)
    commit(db)

    for table in tables:
        assert _live_count(db, table) == 0, f"{table} still holds live rows"
        expected = before[table] + owed if table == "email_send_counts" else before[table]
        assert _archived_count(db, table) == expected, table


def test_archiving_discards_the_mail_it_still_owed(db: Any) -> None:
    """The dispatch row is the only place an attendee's address lives,
    and nothing sweeps the archive. So archiving deletes it rather than
    moving it, and ``email_send_counts`` keeps the tally."""
    event = _event_with_everything(db)
    assert _live_count(db, "email_dispatches") == 2

    archive.archive_item(db, "events", event.id)
    commit(db)

    assert _live_count(db, "email_dispatches") == 0
    assert "email_dispatches_archive" not in archive_metadata.tables
    # The tally travels with the event, so it is in the twin by now.
    counts = archive_metadata.tables["email_send_counts_archive"]
    assert db.execute(select(func.sum(counts.c.failed))).scalar() == 2


def test_restore_puts_every_row_back_unchanged(db: Any) -> None:
    event = _event_with_everything(db)
    event_id = event.id
    tables = ["events", *dependent_tables("events")]
    before = {t: _snapshot(db, t) for t in tables}

    archive.archive_item(db, "events", event_id)
    commit(db)
    archive.restore_item(db, "events", event_id)
    commit(db)

    for table in tables:
        if table == "email_send_counts":
            # Archiving wrote a failed tally for the mail it discarded,
            # so this one table is deliberately not what it was.
            continue
        assert _snapshot(db, table) == before[table], f"{table} came back different"
        assert _archived_count(db, table) == 0, f"{table} left rows in the archive"


def test_ids_survive_the_round_trip(db: Any) -> None:
    """The public slug and every saved edit link are keyed on these."""
    event = _event_with_everything(db)
    event_id = event.id
    occurrence_id = first_occurrence(event).id
    signup_id = db.query(Signup).one().id
    registration_id = db.query(Registration).one().id

    archive.archive_item(db, "events", event_id)
    commit(db)
    archive.restore_item(db, "events", event_id)
    commit(db)

    assert db.query(Occurrence).filter(Occurrence.id == occurrence_id).one().id == occurrence_id
    assert db.query(Signup).filter(Signup.id == signup_id).one().id == signup_id
    assert db.query(Registration).filter(Registration.id == registration_id).one().id == registration_id


def test_purge_leaves_nothing_anywhere(db: Any) -> None:
    event = _event_with_everything(db)
    event_id = event.id
    tables = ["events", *dependent_tables("events")]

    archive.archive_item(db, "events", event_id)
    commit(db)
    archive.purge_item(db, "events", event_id)
    commit(db)

    for table in tables:
        assert _live_count(db, table) == 0, table
        assert _archived_count(db, table) == 0, table


def test_archiving_one_event_leaves_the_other_alone(db: Any) -> None:
    kept = _event_with_everything(db)
    archived = _event_with_everything(db)
    kept_id, archived_id = kept.id, archived.id
    kept_signups = _snapshot(db, "signups")

    archive.archive_item(db, "events", archived_id)
    commit(db)

    assert db.query(Occurrence).filter(Occurrence.event_id == kept_id).count() >= 1
    remaining = _snapshot(db, "signups")
    assert len(remaining) == len(kept_signups) - 1
    assert _archived_count(db, "signups") == 1


def test_an_unknown_root_is_refused(db: Any) -> None:
    """The root name reaches SQL as a table name, so it is checked
    against the four rather than trusted."""
    try:
        archive.archive_item(db, "users", "whatever")
    except ValueError as exc:
        assert "archivable" in str(exc)
    else:
        raise AssertionError("an unknown root should be refused")
