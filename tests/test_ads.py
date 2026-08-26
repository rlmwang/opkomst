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
