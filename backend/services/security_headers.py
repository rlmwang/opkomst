"""Security-headers middleware.

Sets the standard hardening headers on every response:

- ``Content-Security-Policy`` — pinned strict policy that allows
  PrimeVue 4's runtime style injection (``'unsafe-inline'`` for
  styles only — they're injected as ``<style>`` tags by the
  component library, blocking them renders every PrimeVue
  component as unstyled HTML), the OSM tile server, and PDOK
  Locatieserver for the address autocomplete. Scripts get a
  per-response nonce, which the HTML shells stamp on the two blocks
  they inline (the brand and the first-paint payload) — see
  ``routers/spa.py``.
- ``Strict-Transport-Security`` — only set when the request was
  served over HTTPS, so local dev over HTTP isn't accidentally
  upgraded.
- ``X-Content-Type-Options: nosniff`` — disable MIME sniffing.
- ``X-Frame-Options: DENY`` — refuse to be embedded in an iframe.
- ``Referrer-Policy: strict-origin-when-cross-origin`` — leak
  origin only on cross-origin navigations.
- ``Permissions-Policy`` — turn off device APIs we don't use.

The CSP is intentionally tight; loosening it requires editing this
file rather than getting silently overridden by a deeper layer.
"""

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Pinned policy. ``'unsafe-inline'`` for ``style-src`` is required
# because PrimeVue 4 generates component CSS at runtime via
# JavaScript and injects it as ``<style>`` tags. Without this every
# PrimeVue component renders unstyled. The same trade-off is
# documented in CLAUDE.md.
CSP_TEMPLATE = (
    "default-src 'self'; "
    # Hero images are same-origin now: they are served by ``/i/{path}``
    # from wherever they are stored, so no image host appears here or
    # anywhere else a visitor can see.
    "img-src 'self' data: blob: "
    "https://*.tile.openstreetmap.org; "
    "style-src 'self' 'unsafe-inline'; "
    # The HTML shells carry two inline scripts the pages can't work
    # without: the brand (palette, logo, wordmark) and the entity
    # payload that makes a public page interactive on first paint. Both
    # are server-rendered, so they get a per-response nonce rather than
    # ``'unsafe-inline'`` — no attacker-supplied script can guess it.
    "script-src 'self' 'nonce-{nonce}'; "
    # Sentry's regional ingest endpoint for browser-side error
    # reporting. Matches ``VITE_SENTRY_DSN`` (de.sentry.io org).
    "connect-src 'self' "
    "https://api.pdok.nl "
    "https://*.tile.openstreetmap.org "
    "https://*.ingest.de.sentry.io; "
    "font-src 'self' data:; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

# The same policy with the holes advertising needs, served only for
# pages no organisation owns (see ``docs/ads.md``). Two things force
# each hole:
#
# * the ad script and Google's consent dialog load from their own hosts;
# * the creative itself comes from whichever advertiser won the auction,
#   and that host is not knowable in advance, so ``img-src`` and
#   ``frame-src`` cannot be a list.
#
# An organisation's pages never receive this. ``routers/spa.py`` sets
# ``request.state.ads_allowed`` from the brand it resolved, and
# ``tests/test_ads.py`` pins that an organisation-owned page gets the
# strict policy above.
_AD_HOSTS = "https://pagead2.googlesyndication.com https://fundingchoicesmessages.google.com"
CSP_ADS_TEMPLATE = (
    CSP_TEMPLATE.replace(
        "script-src 'self' 'nonce-{nonce}'; ",
        f"script-src 'self' 'nonce-{{nonce}}' {_AD_HOSTS} https://*.googlesyndication.com; ",
    )
    .replace(
        "img-src 'self' data: blob: ",
        "img-src 'self' data: blob: https: ",
    )
    .replace(
        "frame-ancestors 'none'; ",
        "frame-src https:; frame-ancestors 'none'; ",
    )
    .replace(
        "connect-src 'self' ",
        "connect-src 'self' https://pagead2.googlesyndication.com https://*.googlesyndication.com ",
    )
)

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        # Minted before the route runs so the HTML renderer can stamp
        # the same value on the scripts it inlines.
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response: Response = await call_next(request)
        # The route has run by now, so it has already resolved which
        # brand the page wears and said whether this page may carry ads.
        # Anything that never went through a page handler keeps the
        # strict policy.
        template = CSP_ADS_TEMPLATE if getattr(request.state, "ads_allowed", False) else CSP_TEMPLATE
        response.headers["Content-Security-Policy"] = template.format(nonce=nonce)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
        if request.url.scheme == "https":
            # Only when we're actually on HTTPS; setting HSTS on a
            # plain-HTTP response is meaningless and would block dev.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
