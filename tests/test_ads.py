"""Advertising is confined to the pages no organisation owns.

Three rules, each with a test here, because each is the kind that breaks
silently and is noticed by a member of an organisation rather than by
us:

* an organisation's pages carry no ad configuration and never receive
  the loosened Content-Security-Policy;
* a deployment with no ``ADSENSE_CLIENT_ID`` loads no advertising code
  at all, so it keeps the strict policy too, and the slot offers the
  support buttons this app serves itself;
* the loosened policy is loosened in exactly the places advertising
  needs and nowhere else.

Design and reasoning: ``docs/ads.md``.
"""

from __future__ import annotations

import pathlib

import pytest

from backend.services import brand as brand_svc
from backend.services.security_headers import CSP_ADS_TEMPLATE, CSP_TEMPLATE


def test_only_the_house_brand_carries_an_ad_configuration() -> None:
    """``ads`` is the whole switch: null means the page shows nothing,
    and every brand an organisation owns is null."""
    assert brand_svc.payload(brand_svc.HOUSE_BRAND)["ads"] is not None
    for slug in ("rsp", "rood"):
        assert brand_svc.payload(slug)["ads"] is None, slug


def test_the_support_buttons_are_served_from_this_app() -> None:
    """Each service's own button artwork is committed to ``brands/`` and
    served from here, not fetched from their CDNs, so the slot makes no
    third-party request while no ad is being served."""
    ads = brand_svc.payload(brand_svc.HOUSE_BRAND)["ads"]
    assert ads["client_id"] is None, "the test env configures no network"
    assert ads["coffee_button_url"].startswith("/brand/")
    assert ads["patreon_button_url"].startswith("/brand/")


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch):
    """A deployment that has been given a network. ``Settings`` is
    frozen and built at import time, so the copy is swapped in wherever
    it is read rather than mutated."""
    from backend.config import settings

    fake = settings.model_copy(
        update={
            "adsense_client_id": "ca-pub-0000000000000000",
            "adsense_slot_rail": "1111111111",
            "adsense_slot_banner": "2222222222",
        }
    )
    monkeypatch.setattr("backend.services.brand.settings", fake)
    monkeypatch.setattr("backend.routers.spa.settings", fake)
    monkeypatch.setattr("backend.routers.ads_txt.settings", fake)
    monkeypatch.setattr("backend.routers.privacy.settings", fake)
    return fake


def test_configured_ids_reach_the_house_brand_only(configured) -> None:
    """The env var is what turns advertising on, and the brand is what
    decides where it may appear. Both, or nothing."""
    ads = brand_svc.payload(brand_svc.HOUSE_BRAND)["ads"]
    assert ads["client_id"] == "ca-pub-0000000000000000"
    assert ads["rail_slot"] == "1111111111"
    assert ads["banner_slot"] == "2222222222"
    for slug in ("rsp", "rood"):
        assert brand_svc.payload(slug)["ads"] is None, slug


def test_a_house_brand_page_gets_the_ad_policy_once_configured(client, configured) -> None:
    """The other half of the gate: with a network configured, the page
    that may carry ads is served the policy that lets them load."""
    csp = client.get("/events").headers["content-security-policy"]
    assert "https://pagead2.googlesyndication.com" in csp
    assert "https://fundingchoicesmessages.google.com" in csp


def test_an_organisation_page_never_gets_the_ad_policy(client, configured) -> None:
    """The rule that matters most: configuring a network does not open
    an organisation's pages, now or by accident later."""
    csp = client.get("/rsp/events").headers["content-security-policy"]
    assert "googlesyndication" not in csp


def test_ads_txt_is_absent_until_a_publisher_is_configured(client) -> None:
    """An empty or placeholder file is a claim that nobody is
    authorised to sell this inventory. Having nothing to declare is a
    different statement, and a 404 is how it is made."""
    assert client.get("/ads.txt").status_code == 404


def test_ads_txt_declares_google_once_configured(client, configured) -> None:
    """The IAB line every programmatic buyer checks before bidding.
    The ``ca-`` prefix belongs to the ad tag, not to this file: leaving
    it on is the usual reason a publisher id reads as missing."""
    response = client.get("/ads.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.strip() == "google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0"


def test_ads_txt_is_not_swallowed_by_the_spa(client, configured) -> None:
    """It is registered before the catch-all. Served as HTML it would
    read to a crawler as a malformed file rather than as a missing
    one."""
    assert "<html" not in client.get("/ads.txt").text.lower()


def test_the_privacy_policy_carries_no_advertising(client, configured) -> None:
    """The consent dialog links here, and Google asks that the page it
    links to not be one the dialog covers, or "learn more" lands the
    reader back in front of the thing they were reading about. The page
    is served outside the SPA, so it loads no bundle, no ad tag and no
    dialog, whatever the environment is configured with."""
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "googlesyndication" not in response.text
    assert "googlesyndication" not in response.headers["content-security-policy"]


def test_the_privacy_policy_is_not_swallowed_by_the_spa(client) -> None:
    """It is a page in its own right, not a route in the app."""
    body = client.get("/privacy").text
    assert "Privacyverklaring" in body
    assert "OPKOMST_BRAND_INJECTION" not in body


def test_the_crawler_files_answer_head_as_well_as_get(client, configured) -> None:
    """FastAPI's router, unlike Starlette's, does not add HEAD to a GET
    route. A crawler or a link checker that probes with HEAD gets 405
    unless the route says otherwise, and a 405 is indistinguishable
    from a missing file to anything reading it."""
    for path in ("/ads.txt", "/robots.txt", "/privacy"):
        assert client.head(path).status_code == 200, path


def test_robots_is_a_text_file_not_the_app(client) -> None:
    """Without its own route this falls to the SPA fallback and answers
    with HTML, which a crawler reads as an unusable file."""
    response = client.get("/robots.txt")
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.startswith("User-agent:")
    # The API and the sign-in paths are not worth a crawl budget.
    assert "Disallow: /api/" in response.text


def test_the_strict_policy_names_no_ad_host() -> None:
    """The regression guard for the whole feature: whatever else
    changes, the default policy every page gets stays closed."""
    strict = CSP_TEMPLATE.format(nonce="n")
    for host in ("googlesyndication", "google", "doubleclick"):
        assert host not in strict


@pytest.mark.parametrize(
    ("directive", "must_contain"),
    [
        ("script-src", "https://pagead2.googlesyndication.com"),
        ("script-src", "https://fundingchoicesmessages.google.com"),
        ("img-src", "https:"),
        ("frame-src", "https:"),
        ("connect-src", "https://pagead2.googlesyndication.com"),
    ],
)
def test_the_ad_policy_opens_what_advertising_needs(directive: str, must_contain: str) -> None:
    """Each hole is deliberate: the script and the consent dialog load
    from Google's hosts, and the creative comes from whichever
    advertiser won the auction, which is not knowable in advance."""
    policy = {
        part.strip().split(" ", 1)[0]: part.strip()
        for part in CSP_ADS_TEMPLATE.format(nonce="n").split(";")
        if part.strip()
    }
    assert must_contain in policy[directive]


def test_the_ad_policy_keeps_everything_else_shut() -> None:
    """Advertising needs script, image, frame and connect sources. It
    does not need anything else, and nothing else moved."""
    loose = CSP_ADS_TEMPLATE.format(nonce="n")
    for directive in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'"):
        assert directive in loose


def test_an_organisation_page_gets_the_strict_policy(client) -> None:
    """End to end: the header on an organisation's own page names no ad
    host, whatever the deployment's advertising settings are."""
    response = client.get("/rsp/events")
    csp = response.headers["content-security-policy"]
    assert "googlesyndication" not in csp


def test_a_house_brand_page_gets_the_strict_policy_without_a_network(client) -> None:
    """No ``ADSENSE_CLIENT_ID`` means no ad script, no consent dialog
    and no cookie, so there is nothing to open the policy for. The
    loosened policy is not served just because a page could carry ads;
    it is served when a page actually does."""
    response = client.get("/events")
    csp = response.headers["content-security-policy"]
    assert "googlesyndication" not in csp


def test_a_written_page_carries_the_slot_once_configured(client, configured) -> None:
    """The written pages are house-brand pages and they carry ads
    (``docs/ads.md``). The tag, the publisher id and the unit ids all
    have to arrive in the HTML, because there is no bundle here to
    fetch them later."""
    body = client.get("/datumplanner-zonder-account").text
    assert "pagead2.googlesyndication.com" in body
    assert "ca-pub-0000000000000000" in body
    assert '"1111111111"' in body or "1111111111" in body
    assert "2222222222" in body
    csp = client.get("/datumplanner-zonder-account").headers["content-security-policy"]
    assert "https://pagead2.googlesyndication.com" in csp


def test_the_written_pages_advertise_under_a_nonce(client, configured) -> None:
    """The slot is built by an inline script, and the strict-by-default
    ``script-src`` has no ``'unsafe-inline'``. Without the nonce the
    browser drops it and the page silently carries no ad at all."""
    response = client.get("/vrijwilligers-inroosteren")
    nonce = response.headers["content-security-policy"].split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'<script nonce="{nonce}">' in response.text


def test_an_unconfigured_deployment_keeps_the_written_pages_clean(client) -> None:
    """No client id, no tag, no loosened policy: the pages are exactly
    what they were before advertising existed."""
    response = client.get("/aanmeldformulier-zonder-google")
    assert "googlesyndication" not in response.text
    assert "googlesyndication" not in response.headers["content-security-policy"]


def test_the_written_pages_and_the_component_agree_on_the_slot() -> None:
    """The rails, the banner and the breakpoint exist twice: once in
    ``AdSlot.vue`` for the app, once inline in ``templates/content.html``
    because these pages carry no bundle to reach the component. Nothing
    but this test stops the two shapes from drifting."""
    root = pathlib.Path(__file__).resolve().parent.parent
    component = (root / "frontend" / "src" / "public_shared" / "AdSlot.vue").read_text(encoding="utf-8")
    unit = (root / "frontend" / "src" / "public_shared" / "AdUnit.vue").read_text(encoding="utf-8")
    page = (root / "backend" / "templates" / "content.html").read_text(encoding="utf-8")
    assert "(min-width: 1236px)" in component and "(min-width: 1236px)" in page
    for size in ("width: 160px;", "height: 600px;", "width: 320px;", "height: 50px;"):
        assert size in component, size
        assert size in page, size
    # The class the tag looks for, and the attributes it reads off it.
    for token in ('class="adsbygoogle"', "data-ad-client", "data-ad-slot"):
        assert token in unit, token
        assert token.replace('class="adsbygoogle"', '"adsbygoogle"') in page, token
