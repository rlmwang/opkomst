"""Public chapter-agenda endpoint + slug dispatch.

Covers the window split (upcoming / recent-past with the last-full-month
floor), the ``listed`` and ``archived`` exclusions, the slim card DTO,
404s, and the slug helpers that keep ``/e/{ident}`` dispatch unambiguous.
"""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.models import Signup
from backend.schemas.chapters import ChapterPatch
from backend.services import chapters as chapters_svc
from backend.services.agenda import _last_full_month_start
from backend.services.events import now_wallclock
from backend.services.slug import chapter_slug, is_event_slug, new_slug
from tests._helpers.events import make_event


def _chapter(db, name="Testafdeling"):
    ch = chapters_svc.create(db, name=name)
    db.commit()
    return ch


def _agenda(client, slug):
    r = client.get(f"/api/v1/chapters/by-slug/{slug}/agenda")
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else None


# --- window split ---------------------------------------------------------

def test_upcoming_and_recent_past_split(db, client):
    ch = _chapter(db)
    now = now_wallclock()
    make_event(db, name="Upcoming", starts_in=timedelta(days=3), chapter_id=ch.id)
    make_event(db, name="RecentPast", starts_in=timedelta(days=-2), chapter_id=ch.id)
    # An event that ended before the start of the last full calendar
    # month must be excluded from the past section.
    old_start = _last_full_month_start(now) - timedelta(days=5)
    make_event(db, name="Old", starts_in=old_start - now, chapter_id=ch.id)
    db.commit()

    status, j = _agenda(client, ch.slug)
    assert status == 200
    assert [e["name"] for e in j["upcoming"]] == ["Upcoming"]
    past_names = [e["name"] for e in j["past"]]
    assert "RecentPast" in past_names
    assert "Old" not in past_names


def test_event_ending_one_minute_ago_is_past(db, client):
    ch = _chapter(db)
    e = make_event(db, name="JustEnded", starts_in=timedelta(hours=-3), chapter_id=ch.id)
    e.ends_at = now_wallclock() - timedelta(minutes=1)
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert "JustEnded" in [x["name"] for x in j["past"]]
    assert "JustEnded" not in [x["name"] for x in j["upcoming"]]


def test_cutoff_is_first_of_last_month():
    assert _last_full_month_start(datetime(2026, 7, 8, 12, 30)) == datetime(2026, 6, 1)
    # January rolls back across the year boundary.
    assert _last_full_month_start(datetime(2026, 1, 15)) == datetime(2025, 12, 1)


# --- exclusions -----------------------------------------------------------

def test_unlisted_excluded_but_signup_still_resolves(db, client):
    ch = _chapter(db)
    e = make_event(db, name="Hidden", starts_in=timedelta(days=2), chapter_id=ch.id)
    e.listed = False
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert "Hidden" not in [x["name"] for x in j["upcoming"]]
    # The direct sign-up API still resolves the event.
    assert client.get(f"/api/v1/events/by-slug/{e.slug}").status_code == 200


def test_archived_excluded(db, client):
    ch = _chapter(db)
    e = make_event(db, name="Arch", starts_in=timedelta(days=2), chapter_id=ch.id)
    e.archived_at = datetime(2026, 1, 1)
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert "Arch" not in [x["name"] for x in j["upcoming"]]


def test_chapterless_event_on_no_agenda(db, client):
    ch = _chapter(db)
    make_event(db, name="Homeless", starts_in=timedelta(days=2), chapter_id=None)
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert j["upcoming"] == []


# --- DTO + attendee count -------------------------------------------------

def test_card_dto_is_slim(db, client):
    ch = _chapter(db)
    make_event(db, name="E", starts_in=timedelta(days=2), chapter_id=ch.id)
    db.commit()
    _, j = _agenda(client, ch.slug)
    card = j["upcoming"][0]
    assert set(card) == {
        "slug", "name", "topic", "starts_at", "ends_at", "location",
        "image_url", "image_artist_instagram", "attendee_count",
    }
    for leaked in ("source_options", "help_options", "latitude", "longitude", "listed"):
        assert leaked not in card


def test_attendee_count_sums_party_size(db, client):
    ch = _chapter(db)
    e = make_event(db, name="E", starts_in=timedelta(days=2), chapter_id=ch.id)
    db.add(Signup(event_id=e.id, party_size=3))
    db.add(Signup(event_id=e.id, party_size=2))
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert j["upcoming"][0]["attendee_count"] == 5


# --- 404s -----------------------------------------------------------------

def test_unknown_chapter_404(client):
    assert client.get("/api/v1/chapters/by-slug/nope-nope/agenda").status_code == 404


def test_soft_deleted_chapter_404(db, client):
    ch = _chapter(db)
    chapters_svc.archive(db, chapter_id=ch.id)
    db.commit()
    assert client.get(f"/api/v1/chapters/by-slug/{ch.slug}/agenda").status_code == 404


# --- slug helpers / dispatch ----------------------------------------------

@pytest.mark.parametrize("name", ["amsterda", "xxxxxxxx", "Almere", "Den Haag", "x"])
def test_chapter_slug_never_event_shaped(name):
    assert not is_event_slug(chapter_slug(name))


def test_is_event_slug_dispatch():
    assert is_event_slug(new_slug())
    assert not is_event_slug("amsterdam")
    assert not is_event_slug("den-haag")


def test_slug_validator_rejects_event_shape():
    with pytest.raises(ValidationError):
        ChapterPatch(slug=new_slug())


def test_create_disambiguates_slug_collision(db):
    a = chapters_svc.create(db, name="Amsterdam")
    b = chapters_svc.create(db, name="Amsterdam!!")
    db.commit()
    assert a.slug == "amsterdam"
    assert b.slug != a.slug
    assert b.slug.startswith("amsterdam")
