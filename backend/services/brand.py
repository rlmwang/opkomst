"""The brand of a tenant: its palette, logo, wordmark and app name.

Everything that makes the app *look* like a particular organisation
lives in ``brands/{slug}/`` — a ``brand.json`` manifest, a ``tokens.css``
holding the palette as custom properties, and the image files. Nothing
here is compiled into the frontend bundle: the images are served at
``/brand/{slug}/…`` and the palette is inlined into the page ``<head>``,
so a new organisation is a folder plus a row, never a rebuild.

Two consumers:

* ``routers/spa.py`` calls ``head`` to put the palette, the icons and
  the manifest into every HTML shell, and ``payload`` to hand the
  mini-apps their wordmark and logo.
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

# The brand a page wears when no organisation owns what it is showing:
# a link to something that never existed, or whose tenant is gone. Plain
# and unaffiliated — a dead link shouldn't display somebody's logo. It
# carries no images, which is why every image field below is optional.
HOUSE_BRAND = "opkomst"

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


def _ads(slug: str) -> dict[str, Any]:
    """The house brand's ad configuration: the AdSense identifiers when
    the environment carries them, and the support links to offer in the
    slot when it does not. An unset ``ADSENSE_CLIENT_ID`` is the normal
    state, not a misconfiguration; the slot then says so in words rather
    than sitting empty."""
    m = manifest(slug)
    return {
        "client_id": settings.adsense_client_id,
        "rail_slot": settings.adsense_slot_rail,
        "banner_slot": settings.adsense_slot_banner,
        # Shown in the slot when no ad is being served: each service's
        # own button artwork, committed here and served from this app
        # rather than from their CDNs, so an unconfigured deployment
        # still makes no third-party request and needs no CSP hole.
        "coffee_url": settings.support_coffee_url,
        "coffee_button_url": asset_url(slug, m["support_coffee_button"]) if m["support_coffee_button"] else None,
        "patreon_url": settings.support_patreon_url,
        "patreon_button_url": asset_url(slug, m["support_patreon_button"]) if m["support_patreon_button"] else None,
    }


def payload(slug: str) -> dict[str, Any]:
    """What a page or an email needs to render the brand: the names, the
    org link, and both the root-relative and absolute logo URLs. Email
    clients need the absolute one; pages use the short one.

    The image fields are ``None`` for a brand with no files committed:
    the page then renders its wordmark alone, rather than someone
    else's mark. Every brand in the repository has them today; the
    fallback is what keeps adding one from being a prerequisite."""
    m = manifest(slug)
    logo = asset_url(slug, m["logo"]) if m["logo"] else None
    favicon = asset_url(slug, m["favicon"]) if m["favicon"] else None
    return {
        # ``None`` on every brand an organisation owns, which is what
        # says "this page carries no advertising". The page reads the
        # brand it was served with, so the rule is decided here, once,
        # rather than by each surface remembering to ask.
        "ads": _ads(slug) if slug == HOUSE_BRAND else None,
        "slug": slug,
        # Where the organiser app is mounted, and therefore the router's
        # history base. A tenant's app lives under its slug; the house
        # brand belongs to no tenant, so its only page is the 404 at
        # whatever path the visitor typed.
        "app_base": "/" if slug == HOUSE_BRAND else f"/{slug}/",
        # The six colours in literal form. ``tokens.css`` is the palette
        # for anything that can read a custom property; these are for the
        # two places that can't — the first-paint spinner, which renders
        # before the stylesheet is guaranteed to have arrived, and email,
        # where clients don't support ``var()``.
        "palette": m["palette"],
        "app_name": m["app_name"],
        "wordmark": m["wordmark"],
        "org_name": m["org_name"],
        # The house brand's strapline, in both languages. ``None`` for
        # an organisation: their pages carry their own name and nothing
        # of ours.
        "tagline_nl": m["tagline_nl"],
        "tagline_en": m["tagline_en"],
        "org_url": m["org_url"],
        "mail_from_name": m["mail_from_name"],
        "logo_url": logo,
        "logo_absolute_url": f"{_PUBLIC_BASE}{logo}" if logo else None,
        "favicon_url": favicon,
        "favicon_absolute_url": f"{_PUBLIC_BASE}{favicon}" if favicon else None,
    }


@cache
def palette_css(slug: str) -> str:
    """The tenant's ``tokens.css``, read off disk once per process.

    It is inlined into the head rather than linked. At around 3 kB it is
    smaller than the request that would fetch it, and it blocks the
    first paint either way: every page used to hold its paint on a round
    trip for the colours it was about to paint in. Inlining is also what
    lets the boot spinner in each HTML shell use the real token names.
    The shells carried a duplicate ``--boot-*`` palette for exactly one
    reason, that the stylesheet might not have arrived yet."""
    return (BRANDS_DIR / slug / "tokens.css").read_text(encoding="utf-8")


def head(slug: str, nonce: str) -> str:
    """Everything a shell's ``<head>`` needs to wear the brand, in the
    order it is needed: the palette inline, the icons as links, and the
    manifest on ``window`` for the apps.

    Substituted into ``<!-- OPKOMST_BRAND_INJECTION -->``; the Vite dev
    server does the same substitution (see ``vite.config.ts``) so dev and
    prod render the same head.

    ``nonce`` is the per-response CSP nonce minted by
    ``SecurityHeadersMiddleware``: the policy is ``script-src 'self'``,
    so without it the browser refuses to run the one inline block the
    page cannot start without."""
    m = manifest(slug)
    brand_json = json.dumps(payload(slug), ensure_ascii=False)
    lines = [f"<style>{palette_css(slug)}</style>"]
    # A brand without icon files simply doesn't link any; the browser
    # falls back to its own default rather than to another org's mark.
    if m["favicon"]:
        lines.append(f'<link rel="icon" type="image/png" sizes="192x192" href="{asset_url(slug, m["favicon"])}">')
    if m["apple_touch_icon"]:
        lines.append(f'<link rel="apple-touch-icon" sizes="180x180" href="{asset_url(slug, m["apple_touch_icon"])}">')
    lines.append(f'<script nonce="{nonce}">window.__OPKOMST_BRAND__ = {brand_json};</script>')
    return "\n    ".join(lines)
