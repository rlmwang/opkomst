"""Absolute-URL builder for in-email links."""

from urllib.parse import urlencode

from ...config import settings


def build_url(path: str, **params: str) -> str:
    """Build an absolute URL for an in-email link. Always uses
    ``settings.public_base_url`` (validated at boot)."""
    base = str(settings.public_base_url).rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/{path}" if path else base
    if params:
        url = f"{url}?{urlencode(params)}"
    return url
