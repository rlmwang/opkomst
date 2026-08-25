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


def test_the_house_brand_exists_and_carries_no_organisations_mark() -> None:
    """The fallback for pages with no owning organisation. It has a
    palette like any brand, and deliberately no images."""
    house = brand_svc.payload(brand_svc.HOUSE_BRAND)
    assert house["logo_url"] is None
    assert house["favicon_url"] is None
    head = brand_svc.head(brand_svc.HOUSE_BRAND)
    assert f'href="/brand/{brand_svc.HOUSE_BRAND}/tokens.css"' in head
    assert 'rel="icon"' not in head


def test_head_carries_palette_icons_and_window_payload() -> None:
    """What the shells get: the boot colours inline (the spinner paints
    before a linked stylesheet is guaranteed to have arrived), the
    palette stylesheet, both icons, and the brand on ``window``."""
    head = brand_svc.head("rsp")
    assert "--boot-accent:" in head
    assert '<link rel="stylesheet" href="/brand/rsp/tokens.css">' in head
    assert 'rel="icon"' in head and "/brand/rsp/favicon.png" in head
    assert 'rel="apple-touch-icon"' in head and "/brand/rsp/apple-touch-icon.png" in head
    assert "window.__OPKOMST_BRAND__" in head
    assert '"logo_url": "/brand/rsp/logo.png"' in head


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
