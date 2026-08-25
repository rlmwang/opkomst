"""The brand of a tenant: its palette, logo, wordmark and app name.

Everything that makes the app *look* like a particular organisation
lives in ``brands/{slug}/`` — a ``brand.json`` manifest, a ``tokens.css``
holding the palette as custom properties, and the image files. Nothing
here is compiled into the frontend bundle: the files are served at
``/brand/{slug}/…`` and linked from the page ``<head>``, so a new
organisation is a folder plus a row, never a rebuild.

Two consumers:

* ``routers/spa.py`` calls ``head_links`` + ``boot_style`` to put the
  stylesheet, the icons and the first-paint colours into every HTML
  shell, and ``payload`` to hand the mini-apps their wordmark and logo.
* ``services/mail.py`` calls ``payload`` for the same values in email,
  where the logo has to be an absolute URL.

The manifest is read once per process and cached; brand files change
only on deploy.
"""

import json
import pathlib
from functools import cache
from typing import Any

from ..config import settings

BRANDS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "brands"

# The tenant whose brand every surface uses. Becomes a per-request
# lookup when tenants land (design-tenants-and-branding.md, step 5).
DEFAULT_BRAND = "rsp"

_PUBLIC_BASE = str(settings.public_base_url).rstrip("/")


@cache
def manifest(slug: str) -> dict[str, Any]:
    """The tenant's parsed ``brand.json``. Raises if the folder or the
    manifest is missing — a deployment without its brand is broken, not
    something to paper over with defaults."""
    path = BRANDS_DIR / slug / "brand.json"
    return json.loads(path.read_text(encoding="utf-8"))


def asset_url(slug: str, filename: str) -> str:
    """Root-relative URL of one brand file, as the browser sees it."""
    return f"/brand/{slug}/{filename}"


def payload(slug: str) -> dict[str, Any]:
    """What a page or an email needs to render the brand: the names, the
    org link, and both the root-relative and absolute logo URLs. Email
    clients need the absolute one; pages use the short one."""
    m = manifest(slug)
    logo = asset_url(slug, m["logo"])
    return {
        "slug": slug,
        # The six colours in literal form. ``tokens.css`` is the palette
        # for anything that can read a custom property; these are for the
        # two places that can't — the first-paint spinner, which renders
        # before the stylesheet is guaranteed to have arrived, and email,
        # where clients don't support ``var()``.
        "palette": m["palette"],
        "app_name": m["app_name"],
        "wordmark": m["wordmark"],
        "org_name": m["org_name"],
        "org_url": m["org_url"],
        "mail_from_name": m["mail_from_name"],
        "logo_url": logo,
        "logo_absolute_url": f"{_PUBLIC_BASE}{logo}",
        "favicon_url": asset_url(slug, m["favicon"]),
        "favicon_absolute_url": f"{_PUBLIC_BASE}{asset_url(slug, m['favicon'])}",
    }


def head(slug: str) -> str:
    """Everything a shell's ``<head>`` needs to wear the brand, in the
    order it is needed: the first-paint colours inline, the palette
    stylesheet and icons as links, and the manifest on ``window`` for
    the Vue apps.

    The boot colours are the one place a brand's colours are repeated —
    inside its own manifest rather than across four files — because the
    spinner paints before a linked stylesheet has necessarily arrived.

    Substituted into ``<!-- OPKOMST_BRAND_INJECTION -->``; the Vite dev
    server does the same substitution (see ``vite.config.ts``) so dev and
    prod render the same head."""
    m = manifest(slug)
    boot = m["palette"]
    inline_boot = (
        "<style>:root{"
        f"--boot-bg:{boot['bg']};"
        f"--boot-surface:{boot['surface']};"
        f"--boot-fg:{boot['fg']};"
        f"--boot-fg-muted:{boot['fg_muted']};"
        f"--boot-accent:{boot['accent']};"
        f"--boot-border:{boot['border']};"
        "}</style>"
    )
    brand_json = json.dumps(payload(slug), ensure_ascii=False)
    return (
        f"{inline_boot}\n"
        f'    <link rel="stylesheet" href="{asset_url(slug, "tokens.css")}">\n'
        f'    <link rel="icon" type="image/png" sizes="192x192" href="{asset_url(slug, m["favicon"])}">\n'
        f'    <link rel="apple-touch-icon" sizes="180x180" href="{asset_url(slug, m["apple_touch_icon"])}">\n'
        f"    <script>window.__OPKOMST_BRAND__ = {brand_json};</script>"
    )
