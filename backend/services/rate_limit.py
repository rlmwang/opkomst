"""Per-IP rate limiting for public-facing mutations.

We expose three unauthenticated POST endpoints — register, login,
and the public sign-up — each of which can be hammered to inflate
DB rows, brute-force credentials, or burn email budget. ``slowapi``
wraps starlette/FastAPI with Flask-Limiter-style decorators.

Limits are deliberately generous for legitimate use (a real human
clicking a sign-up form once at an event) but tight enough that an
attacker can't spin up thousands of inserts. Tighten in the
deployment env via ``RATE_LIMIT_*`` overrides if needed.

Storage is in-process — fine for a single-uvicorn-worker dev setup
or a single-replica production. For multi-worker / multi-replica,
configure ``RATE_LIMIT_STORAGE_URI`` to a Redis URL; slowapi
auto-uses it when set.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_func(request) -> str:  # type: ignore[no-untyped-def]
    """Per-IP key. Behind a reverse proxy that sets
    ``X-Forwarded-For``, slowapi's ``get_remote_address`` reads it
    only when ``app.state.limiter`` is told to trust the header.
    For now we rely on the proxy stripping spoofed values."""
    return get_remote_address(request)


limiter = Limiter(
    key_func=_key_func,
    storage_uri=os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://"),
    # Default fallback applied when a route doesn't declare its own
    # limit — generous, just a safety net against runaway scripts.
    default_limits=["120/minute"],
)
