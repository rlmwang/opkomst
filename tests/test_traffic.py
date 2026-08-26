"""Counting is not tracking, and this is what keeps it that way.

The design in ``docs/analytics.md`` rests on one claim: the traffic
tables hold aggregates that were never personal. A claim like that
decays quietly. Somebody adds a country column for a good reason, then
a user agent for a better one, and a year later the disclosure on every
public page is false and nobody remembers when it stopped being true.

The first test here is the one that matters. The rest check the
counting works.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models.traffic import ACTIONS, SURFACES, TrafficCount
from backend.services import traffic


def test_the_table_cannot_hold_anything_about_a_person() -> None:
    """The column list is pinned. Widening it means changing this test,
    which means saying out loud what is being collected and why.

    Every name here is either the aggregate itself or bookkeeping. None
    of them can hold an address, an agent string, a referrer, a
    session, or the identity of an event somebody was looking at."""
    assert {c.name for c in TrafficCount.__table__.columns} == {
        "id",
        "day",
        "surface",
        "action",
        "count",
        "created_at",
        "updated_at",
    }


def test_surfaces_are_route_classes_not_identifiers() -> None:
    """A surface is a kind of page. If one of these ever looks like a
    slug, an id or a path with a variable in it, the table has started
    recording which thing was looked at rather than what kind."""
    for surface in SURFACES:
        assert surface.replace("_", "").isalpha(), surface
        assert surface.islower(), surface


def test_recording_counts_and_flushing_writes(db) -> None:
    traffic.flush()  # start from a clean tally
    for _ in range(3):
        traffic.record("root")
    traffic.record("public_event", "submit")
    assert traffic.flush() == 2

    rows = {(r.surface, r.action): r.count for r in db.query(TrafficCount).all()}
    assert rows[("root", "view")] >= 3
    assert rows[("public_event", "submit")] >= 1


def test_a_second_flush_adds_rather_than_replaces(db) -> None:
    """Two workers flushing the same minute must add up. The upsert is
    what does that, and getting it wrong would look like traffic
    quietly capping out."""
    traffic.flush()
    traffic.record("root")
    traffic.flush()
    first = db.query(TrafficCount).filter_by(day=date.today(), surface="root", action="view").one().count

    traffic.record("root")
    traffic.flush()
    db.expire_all()
    second = db.query(TrafficCount).filter_by(day=date.today(), surface="root", action="view").one().count
    assert second == first + 1


@pytest.mark.parametrize(
    ("surface", "action"),
    [("nonsense", "view"), ("root", "clicked"), ("/e/abc12345", "view")],
)
def test_an_unknown_name_is_refused_not_invented(surface: str, action: str, db) -> None:
    """A typo should not quietly create a new kind of row that a report
    then has to explain, and a slug should never become a surface."""
    traffic.flush()
    before = db.query(TrafficCount).count()
    traffic.record(surface, action)
    assert traffic.flush() == 0
    db.expire_all()
    assert db.query(TrafficCount).count() == before


def test_flush_survives_a_broken_database(monkeypatch) -> None:
    """A page view is not worth failing a request over. If the database
    is unreachable the count is dropped and the request still
    succeeds."""

    def explode() -> None:
        raise RuntimeError("no database")

    traffic.flush()
    traffic.record("root")
    monkeypatch.setattr("backend.services.traffic.SessionLocal", explode)
    assert traffic.flush() == 0


def test_actions_are_the_two_that_form_a_funnel() -> None:
    """A view and a completion. The ratio between them on one surface
    is the only funnel this app measures, and adding a third action
    would mean adding a question it answers."""
    assert set(ACTIONS) == {"view", "submit"}
