"""Public chapter-agenda endpoint + chapter slugs.

Covers the window split (upcoming / recent-past, both ends bounded by
the owning tenant's ``agenda_future_days`` / ``agenda_past_days``), the
``listed`` and ``archived`` exclusions, the slim card DTO, 404s, and the
slug rules that let the agenda live at ``/{tenant}/{chapter}`` next to
the organiser app's own pages.

The settings endpoint that writes those two numbers is covered in
``tests/test_tenant_settings.py``; here they are set on the row
directly, because what is under test is the read.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import Registration, Signup, Tenant
from backend.schemas.chapters import ChapterPatch
from backend.services import chapters as chapters_svc
from backend.services.events import now_wallclock
from backend.services.slug import RESERVED_SLUGS, chapter_slug
from tests._helpers.events import first_occurrence, make_event


def _chapter(db, name="Testafdeling"):
    ch = chapters_svc.create(db, name=name)
    db.commit()
    return ch


def _window(db, *, future_days=None, past_days=None):
    """Set the tenant's agenda window. The chapter fixture's tenant is
    the one every test in this file reads through."""
    tenant = db.query(Tenant).filter(Tenant.slug == "rsp").one()
    if future_days is not None:
        tenant.agenda_future_days = future_days
    if past_days is not None:
        tenant.agenda_past_days = past_days
    db.commit()
    return tenant


def _agenda(client, slug, tenant="rsp"):
    r = client.get(f"/api/v1/tenants/{tenant}/agenda/{slug}")
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else None


# --- window split ---------------------------------------------------------


def test_upcoming_and_recent_past_split(db, client):
    ch = _chapter(db)
    _window(db, future_days=31, past_days=60)
    make_event(db, name="Upcoming", starts_in=timedelta(days=3), chapter_id=ch.id)
    make_event(db, name="RecentPast", starts_in=timedelta(days=-2), chapter_id=ch.id)
    # Outside the window in each direction: one past the future edge,
    # one behind the past floor. Neither section may hold them.
    make_event(db, name="TooFar", starts_in=timedelta(days=40), chapter_id=ch.id)
    make_event(db, name="Old", starts_in=timedelta(days=-70), chapter_id=ch.id)
    db.commit()

    status, j = _agenda(client, ch.slug)
    assert status == 200
    assert [e["name_nl"] for e in j["upcoming"]] == ["Upcoming"]
    past_names = [e["name_nl"] for e in j["past"]]
    assert "RecentPast" in past_names
    assert "Old" not in past_names
    assert "TooFar" not in past_names


def test_widening_the_future_window_surfaces_an_event(db, client):
    """The reason the setting exists: an organisation that programmes a
    season ahead sets the window to reach it, and the occurrence that
    was already materialised shows up."""
    ch = _chapter(db)
    _window(db, future_days=31)
    make_event(db, name="Season", starts_in=timedelta(days=48), chapter_id=ch.id)
    db.commit()

    _, j = _agenda(client, ch.slug)
    assert j["upcoming"] == []

    _window(db, future_days=90)
    _, j = _agenda(client, ch.slug)
    assert [e["name_nl"] for e in j["upcoming"]] == ["Season"]


def test_narrowing_the_past_window_drops_an_event(db, client):
    ch = _chapter(db)
    _window(db, past_days=60)
    make_event(db, name="LastMonth", starts_in=timedelta(days=-40), chapter_id=ch.id)
    db.commit()

    _, j = _agenda(client, ch.slug)
    assert [e["name_nl"] for e in j["past"]] == ["LastMonth"]

    _window(db, past_days=7)
    _, j = _agenda(client, ch.slug)
    assert j["past"] == []


def test_window_comes_from_the_chapters_own_tenant(db, client):
    """A public read binds no tenant of its own, so the window has to be
    read off the row the URL resolved to, not off whatever was bound."""
    ch = _chapter(db)
    _window(db, future_days=90)
    make_event(db, name="Season", starts_in=timedelta(days=48), chapter_id=ch.id)
    db.commit()

    other = Tenant(slug="other", name="Other", agenda_future_days=7)
    db.add(other)
    db.commit()

    _, j = _agenda(client, ch.slug)
    assert [e["name_nl"] for e in j["upcoming"]] == ["Season"]


def test_event_ending_one_minute_ago_is_past(db, client):
    ch = _chapter(db)
    e = make_event(db, name="JustEnded", starts_in=timedelta(hours=-3), chapter_id=ch.id)
    # Boundary is on the occurrence, not the event: an occurrence that ended
    # one minute ago must fall in the past section, not upcoming.
    occ = first_occurrence(e)
    occ.ends_at = now_wallclock() - timedelta(minutes=1)
    occ.starts_at = occ.ends_at - timedelta(hours=2)
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert "JustEnded" in [x["name_nl"] for x in j["past"]]
    assert "JustEnded" not in [x["name_nl"] for x in j["upcoming"]]


# --- exclusions -----------------------------------------------------------


def test_unlisted_excluded_but_signup_still_resolves(db, client):
    ch = _chapter(db)
    e = make_event(db, name="Hidden", starts_in=timedelta(days=2), chapter_id=ch.id)
    e.listed = False
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert "Hidden" not in [x["name_nl"] for x in j["upcoming"]]
    # The direct sign-up API still resolves the event (per-occurrence slug).
    assert client.get(f"/api/v1/event/by-slug/{first_occurrence(e).slug}").status_code == 200


def test_archived_excluded(db, client):
    ch = _chapter(db)
    e = make_event(db, name="Arch", starts_in=timedelta(days=2), chapter_id=ch.id)
    e.archived_at = datetime(2026, 1, 1)
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert "Arch" not in [x["name_nl"] for x in j["upcoming"]]


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
        "slug",
        "name_nl",
        "name_en",
        "topic_nl",
        "topic_en",
        "starts_at",
        "ends_at",
        "location",
        "image_url",
        "image_artist_instagram",
        "attendee_count",
        "index",
        "total_sessions",
    }
    for leaked in ("source_options", "help_options", "latitude", "longitude", "listed"):
        assert leaked not in card


def test_attendee_count_sums_party_size(db, client):
    ch = _chapter(db)
    e = make_event(db, name="E", starts_in=timedelta(days=2), chapter_id=ch.id)
    occ = first_occurrence(e)
    # Attendee count sums party_size over the occurrence's bookings.
    for size in (3, 2):
        reg = Registration(event_id=e.id, party_size=size)
        db.add(reg)
        db.flush()
        db.add(Signup(registration_id=reg.id, occurrence_id=occ.id))
    db.commit()
    _, j = _agenda(client, ch.slug)
    assert j["upcoming"][0]["attendee_count"] == 5


# --- 404s -----------------------------------------------------------------


def test_unknown_chapter_404(client):
    assert client.get("/api/v1/tenants/rsp/agenda/nope-nope").status_code == 404


def test_unknown_organisation_404(client):
    """An unknown organisation answers exactly like an unknown chapter,
    so the surface can't be walked for which organisations exist."""
    assert client.get("/api/v1/tenants/nope/agenda/whatever").status_code == 404


def test_soft_deleted_chapter_404(db, client):
    ch = _chapter(db)
    chapters_svc.archive(db, chapter_id=ch.id)
    db.commit()
    assert client.get(f"/api/v1/tenants/rsp/agenda/{ch.slug}").status_code == 404


# --- slug helpers / dispatch ----------------------------------------------


@pytest.mark.parametrize("name", ["Almere", "Den Haag", "Utrecht Centrum", "x"])
def test_chapter_slug_is_readable_kebab(name):
    slug = chapter_slug(name)
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)


def test_a_chapter_cannot_be_named_after_a_page_of_the_app(db):
    """``/{tenant}/{chapter}`` and ``/{tenant}/event`` are one
    namespace, and the app wins: a chapter called Event lands on
    ``event-2``."""
    ch = chapters_svc.create(db, name="Event")
    db.commit()
    assert ch.slug == "event-2"


def test_slug_validator_rejects_a_page_name():
    with pytest.raises(ValidationError):
        ChapterPatch(slug="event")


def test_reserved_slugs_cover_every_first_level_route(db):
    """The dev server splits ``/{tenant}/{second}`` on the same set, so
    the two lists have to agree. If a route is added to the SPA without
    adding it here, a chapter can already be holding that slug and would
    shadow the new page.

    Read out of ``vite.config.ts`` rather than repeated here: a
    hand-copied list is a list that drifts, and this one had already
    lost ``quizzes`` before the sixth product arrived to notice."""
    config = (Path(__file__).resolve().parents[1] / "frontend" / "vite.config.ts").read_text()
    block = re.search(r"const appRoutes = new Set\(\[(.*?)\]\);", config, re.S)
    assert block is not None, "appRoutes moved; this test is the only thing keeping the two lists in step"
    app_routes = {name for name in re.findall(r'"([^"]*)"', block.group(1)) if name}
    assert app_routes, "appRoutes parsed empty"
    assert app_routes <= RESERVED_SLUGS, sorted(app_routes - RESERVED_SLUGS)


def test_two_organisations_may_each_have_an_amsterdam(db):
    """The reason the agenda moved under its organisation."""
    from backend.services import tenancy

    ours = chapters_svc.create(db, name="Amsterdam")
    db.commit()

    other = Tenant(slug="other", name="Other")
    db.add(other)
    db.commit()
    with tenancy.use(other.id, other.slug):
        theirs = chapters_svc.create(db, name="Amsterdam")
        db.commit()

    assert ours.slug == theirs.slug == "amsterdam"


def test_create_disambiguates_slug_collision(db):
    a = chapters_svc.create(db, name="Amsterdam")
    b = chapters_svc.create(db, name="Amsterdam!!")
    db.commit()
    assert a.slug == "amsterdam"
    assert b.slug != a.slug
    assert b.slug.startswith("amsterdam")
