"""Link-preview ``og:image`` is per-entity for every ``OrgEntity`` surface.

Every ``OrgEntity`` (event / datepoll / roster / form) carries an
``image_url`` on its spine, and the organiser expects the image they
uploaded to show in WhatsApp / Slack / iMessage previews. The bug this
guards: three of the four builders hardcoded the favicon and ignored the
entity's own ``image_url``, so only events ever got a real card.

The builders are pure functions over the loaded row, so we exercise them
directly on unpersisted model instances rather than rendering the full
SPA HTML shell (which needs the built ``dist/`` files).
"""

import pytest

from backend.models import Chapter, Datepoll, Event, Form, Occurrence, Roster
from backend.routers import spa
from backend.services import brand as brand_svc

_HERO = "https://raw.githubusercontent.com/x/y/hero.jpg"
# The builders take the brand of the organisation that owns the entity;
# these are pure-function tests, so the tenant's brand is passed in
# directly rather than resolved from a row.
_BRAND = "rsp"
_FAVICON = brand_svc.payload(_BRAND)["favicon_absolute_url"]


def _event(image_url):
    # The event builder reads the event through its occurrence; a set
    # ``topic`` keeps it off the "{location} · {date}" description branch
    # so ``starts_at`` is never read.
    event = Event(name_nl="Bokslessen", topic_nl="<p>kom langs</p>", location="Zaal", image_url=image_url)
    return spa._build_head_meta(Occurrence(event=event), "slug1", _BRAND)


def _datepoll(image_url):
    return spa._build_datepoll_head_meta(
        Datepoll(name_nl="Prik", description_nl=None, image_url=image_url), "slug2", _BRAND
    )


def _form(image_url):
    return spa._build_form_head_meta(Form(name_nl="Aanmelden", image_url=image_url), "slug3", _BRAND)


def _roster(image_url):
    return spa._build_roster_head_meta(
        Roster(name_nl="Corvee", description_nl=None, image_url=image_url), "slug4", _BRAND
    )


_BUILDERS = [_event, _datepoll, _form, _roster]


@pytest.mark.parametrize("build", _BUILDERS)
def test_uploaded_image_becomes_the_og_image(build):
    head = build(_HERO)
    assert f'<meta property="og:image" content="{_HERO}">' in head
    assert f'<meta name="twitter:image" content="{_HERO}">' in head
    assert '<meta name="twitter:card" content="summary_large_image">' in head


@pytest.mark.parametrize("build", _BUILDERS)
def test_no_image_falls_back_to_the_owning_organisations_favicon(build):
    head = build(None)
    assert f'<meta property="og:image" content="{_FAVICON}">' in head
    assert '<meta name="twitter:card" content="summary">' in head


def test_chapter_agenda_has_no_image_and_uses_the_favicon():
    # A chapter has no image_url, so its agenda card is always the favicon.
    head = spa._build_chapter_head_meta(Chapter(name="Utrecht"), "utrecht", _BRAND)
    assert f'<meta property="og:image" content="{_FAVICON}">' in head
    assert '<meta name="twitter:card" content="summary">' in head


def test_the_house_brand_has_no_favicon_so_its_card_has_no_image():
    """An unknown slug belongs to no organisation, so the page wears the
    house brand — which has no image files, and therefore no image
    tags rather than a borrowed logo."""
    head = spa._build_chapter_head_meta(Chapter(name="Utrecht"), "utrecht", brand_svc.HOUSE_BRAND)
    assert "og:image" not in head
    assert "twitter:image" not in head
