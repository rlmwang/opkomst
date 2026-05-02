"""Security-headers middleware.

Sets the standard hardening headers on every response:

- ``Content-Security-Policy`` — pinned strict policy that allows
  PrimeVue 4's runtime style injection (``'unsafe-inline'`` for
  styles only — they're injected as ``<style>`` tags by the
  component library, blocking them renders every PrimeVue
  component as unstyled HTML), the OSM tile server, and PDOK
  Locatieserver for the address autocomplete.
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

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Pinned policy. ``'unsafe-inline'`` for ``style-src`` is required
# because PrimeVue 4 generates component CSS at runtime via
# JavaScript and injects it as ``<style>`` tags. Without this every
# PrimeVue component renders unstyled. The same trade-off is
# documented in CLAUDE.md.
CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self' "
    "https://api.pdok.nl "
    "https://*.tile.openstreetmap.org; "
    "font-src 'self' data:; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
        if request.url.scheme == "https":
            # Only when we're actually on HTTPS; setting HSTS on a
            # plain-HTTP response is meaningless and would block dev.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
