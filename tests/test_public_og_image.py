"""Link-preview ``og:image`` is per-entity for every ``OrgEntity`` surface.

Every ``OrgEntity`` (event / datepoll / roster / form) carries an
``image_path`` on its spine, and the organiser expects the image they
uploaded to show in WhatsApp / Slack / iMessage previews. The bug this
guards: three of the four builders hardcoded the favicon and ignored the
entity's own image, so only events ever got a real card.

The card carries this app's own URL for the image, never the storage
host's: a link preview is one of the places the hosting would otherwise
be on show.

The builders are pure functions over the loaded row, so we exercise them
directly on unpersisted model instances rather than rendering the full
SPA HTML shell (which needs the built ``dist/`` files).
"""

import pytest

from backend.models import Chapter, Datepoll, Event, Form, Occurrence, Roster
from backend.routers import spa
from backend.services import brand as brand_svc
from backend.services import image as image_svc

_PATH = "events/ev1/1700000000000.jpg"
_HERO = image_svc.public_url(_PATH)
# The builders take the brand of the organisation that owns the entity;
# these are pure-function tests, so the tenant's brand is passed in
# directly rather than resolved from a row.
_BRAND = "rsp"
_FAVICON = brand_svc.payload(_BRAND)["favicon_absolute_url"]


def _event(image_path):
    # The event builder reads the event through its occurrence; a set
    # ``topic`` keeps it off the "{location} · {date}" description branch
    # so ``starts_at`` is never read.
    event = Event(name_nl="Bokslessen", topic_nl="<p>kom langs</p>", location="Zaal", image_path=image_path)
    return spa._build_head_meta(Occurrence(event=event), "slug1", _BRAND)


def _datepoll(image_path):
    return spa._build_datepoll_head_meta(
        Datepoll(name_nl="Prik", description_nl=None, image_path=image_path), "slug2", _BRAND
    )


def _form(image_path):
    return spa._build_form_head_meta(
        Form(name_nl="Aanmelden", mode="survey", image_path=image_path), "slug3", _BRAND
    )


def _roster(image_path):
    return spa._build_roster_head_meta(
        Roster(name_nl="Corvee", description_nl=None, image_path=image_path), "slug4", _BRAND
    )


_BUILDERS = [_event, _datepoll, _form, _roster]


@pytest.mark.parametrize(
    ("mode", "prefix"),
    [("survey", "f"), ("quiz", "q"), ("compass", "k")],
)
def test_the_canonical_url_names_the_page_the_form_is_actually_on(mode, prefix):
    """One head builder, three products: a quiz's preview card has to
    link to ``/q/…`` and a kompas's to ``/k/…``, not to the
    questionnaire's prefix (``docs/design-kompas.md`` 1.2)."""
    head = spa._build_form_head_meta(Form(name_nl="Aanmelden", mode=mode), "slug3", _BRAND)
    assert f'<meta property="og:url" content="{spa._PUBLIC_BASE}/{prefix}/slug3">' in head


@pytest.mark.parametrize("build", _BUILDERS)
def test_uploaded_image_becomes_the_og_image(build):
    head = build(_PATH)
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


def test_the_house_brand_shares_its_own_mark_and_nobody_elses():
    """A page no organisation owns wears the house brand, which has its
    own icon now, so a shared link shows that rather than nothing. What
    it must never show is an organisation's logo on a page that is not
    theirs."""
    head = spa._build_chapter_head_meta(Chapter(name="Utrecht"), "utrecht", brand_svc.HOUSE_BRAND)
    house_favicon = brand_svc.payload(brand_svc.HOUSE_BRAND)["favicon_absolute_url"]
    assert f'<meta property="og:image" content="{house_favicon}">' in head
    assert f"/brand/{brand_svc.HOUSE_BRAND}/" in house_favicon
    for slug in ("rsp", "rood"):
        assert f"/brand/{slug}/" not in head, slug
