"""The brand is data, not code.

Everything visual about an organisation lives in ``brands/{tenant}/``.
These tests pin the contract that makes "add a folder" enough: the
manifest carries every key the app reads, the head injection carries the
palette + the icons + the window payload, and email renders the logo as
an absolute URL (mail clients can't resolve a root-relative one).

``scripts/check_brand_tokens.py`` covers the other half — that no colour
or logo leaks back into the frontend or the templates.
"""

from __future__ import annotations

import json
from typing import Any

from backend.services import brand as brand_svc
from backend.services import tenancy
from backend.services.mail import render

REQUIRED_KEYS = {
    "app_name",
    "wordmark",
    "org_name",
    "org_url",
    "logo",
    "favicon",
    "apple_touch_icon",
    "mail_from_name",
    "palette",
    # The house brand's strapline; null on an organisation's.
    "tagline_nl",
    "tagline_en",
    # The support buttons the advertising slot offers when it is not
    # showing an ad. Only the house brand carries any, because only its
    # pages ever show the slot, but every manifest names the keys so the
    # app reads one shape everywhere.
    "support_coffee_button",
    "support_patreon_button",
}
REQUIRED_PALETTE_KEYS = {"bg", "surface", "fg", "fg_muted", "accent", "border"}


def _brand_dirs() -> list[Any]:
    return sorted(p for p in brand_svc.BRANDS_DIR.iterdir() if p.is_dir())


def test_every_brand_folder_is_complete() -> None:
    """A brand folder is a contract: the manifest names every key the
    app reads, the palette is complete, and every file it names exists
    next to it. Image fields may be ``null`` — the house brand carries
    no logo, so a page with no owning organisation shows a wordmark
    rather than somebody else's mark — but a named file must be there."""
    assert _brand_dirs(), "no brands on disk"
    for directory in _brand_dirs():
        manifest = json.loads((directory / "brand.json").read_text(encoding="utf-8"))
        missing = REQUIRED_KEYS - manifest.keys()
        assert not missing, f"{directory.name}: brand.json is missing {sorted(missing)}"
        palette_missing = REQUIRED_PALETTE_KEYS - manifest["palette"].keys()
        assert not palette_missing, f"{directory.name}: palette is missing {sorted(palette_missing)}"
        assert (directory / "tokens.css").is_file(), f"{directory.name}: no tokens.css"
        for key in ("logo", "favicon", "apple_touch_icon"):
            if manifest[key] is None:
                continue
            assert (directory / manifest[key]).is_file(), f"{directory.name}: {key} file is missing"


def test_the_house_brand_carries_its_own_mark_and_nobody_elses() -> None:
    """The house brand is a brand in its own right now: it has its own
    logo, icons and strapline, all served from its own folder. What it
    must never carry is an organisation's mark, which is a different
    statement from carrying none."""
    house = brand_svc.payload(brand_svc.HOUSE_BRAND)
    for key in ("logo_url", "favicon_url"):
        assert house[key].startswith(f"/brand/{brand_svc.HOUSE_BRAND}/"), key
    assert house["tagline_nl"] and house["tagline_en"]
    head = brand_svc.head(brand_svc.HOUSE_BRAND, "nonce")
    assert f'href="/brand/{brand_svc.HOUSE_BRAND}/favicon.png"' in head
    assert 'rel="icon"' in head
    # No other brand's folder is ever referenced from this one's head.
    for slug in ("rsp", "rood"):
        assert f"/brand/{slug}/" not in head, slug


def test_only_the_house_brand_has_a_tagline() -> None:
    """An organisation's pages carry their name, not our slogan."""
    for slug in ("rsp", "rood"):
        assert brand_svc.payload(slug)["tagline_nl"] is None, slug
        assert brand_svc.payload(slug)["tagline_en"] is None, slug


def test_the_inline_brand_script_carries_the_csp_nonce() -> None:
    """``script-src 'self'`` blocks inline scripts, so the one block the
    page cannot start without wears the per-response nonce. Without it
    the browser refuses to run it and the app never mounts — which is
    exactly what happened the first time a second tenant was served."""
    head = brand_svc.head("rsp", "n0nc3-value")
    assert '<script nonce="n0nc3-value">window.__OPKOMST_BRAND__' in head


def test_head_carries_palette_icons_and_window_payload() -> None:
    """What the shells get: the palette inline, both icons, and the
    brand on ``window``. The palette is inlined rather than linked so
    the first paint does not wait on a round-trip for the colours it is
    about to paint in."""
    head = brand_svc.head("rsp", "nonce")
    assert "--brand-red:" in head
    assert "<style>" in head
    assert '<link rel="stylesheet"' not in head
    assert 'rel="icon"' in head and "/brand/rsp/favicon.png" in head
    assert 'rel="apple-touch-icon"' in head and "/brand/rsp/apple-touch-icon.png" in head
    assert "window.__OPKOMST_BRAND__" in head
    assert '"logo_url": "/brand/rsp/logo.png"' in head


def test_a_served_page_can_actually_run_its_inline_scripts(client) -> None:
    """End to end: the nonce in the response's CSP is the nonce on the
    page's inline scripts, so the browser runs them. This is the guard
    for the class of bug where a page renders its shell and then sits on
    the spinner forever."""
    response = client.get("/e/nosuchslug")
    if response.status_code == 404:  # no frontend build in this checkout
        return
    nonce = response.headers["content-security-policy"].split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'<script nonce="{nonce}">window.__OPKOMST_BRAND__' in response.text


def test_email_renders_the_brand_with_an_absolute_logo() -> None:
    """Mail clients can't resolve ``/brand/rsp/logo.png``, so the event
    chrome uses the absolute URL, and the palette is interpolated as
    literal values because ``var()`` doesn't work in email either."""
    _subject, html = render(
        "reminder.html",
        {
            "event_name": "Demo",
            "event_date": "1 januari",
            "event_time": "20:00",
            "event_location": "Buurthuis",
            "event_url": "https://example.test/e/abc",
            "topic": None,
            "ics_url": "https://example.test/e/abc/event.ics",
        },
        locale="nl",
    )
    payload = brand_svc.payload("rsp")
    assert payload["logo_absolute_url"] in html
    assert payload["org_url"] in html
    assert payload["palette"]["accent"] in html
    assert "/rsp-logo.png" not in html


def test_a_brand_without_a_logo_renders_its_wordmark_in_email(monkeypatch) -> None:
    """A brand with no logo file renders its wordmark as text. An
    ``<img>`` pointing at nothing is a broken box in a mail client,
    showing the alt text clipped to the image's width, so the chrome
    falls back to words, the same rule ``BrandMark.svelte`` follows on the
    page.

    Every brand committed today has a logo, so the branch is exercised
    against a payload with the field emptied rather than against
    whichever brand happens to lack one this month."""
    house = dict(brand_svc.payload(brand_svc.HOUSE_BRAND))
    house["logo_absolute_url"] = None
    house["logo_url"] = None
    monkeypatch.setattr("backend.services.brand.payload", lambda _slug: house)
    with tenancy.use("t-house", brand_svc.HOUSE_BRAND):
        _subject, html = render(
            "reminder.html",
            {
                "event_name": "Demo",
                "event_date": "1 januari",
                "event_time": "20:00",
                "event_location": "Buurthuis",
                "event_url": "https://example.test/e/abc",
                "topic": None,
                "ics_url": "https://example.test/e/abc/event.ics",
            },
            locale="nl",
        )
    assert 'src="None"' not in html
    assert house["wordmark"] in html
