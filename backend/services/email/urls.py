"""Absolute-URL builder for in-email links."""

import os
from urllib.parse import urlencode


def build_url(path: str, **params: str) -> str:
    """Build an absolute URL for an in-email link. Always reads from
    ``PUBLIC_BASE_URL``; a missing value is a configuration bug, not
    something to paper over with a localhost fallback."""
    base = os.environ["PUBLIC_BASE_URL"].rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/{path}" if path else base
    if params:
        url = f"{url}?{urlencode(params)}"
    return url
