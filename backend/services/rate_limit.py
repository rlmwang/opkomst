"""Per-IP rate limiting for public-facing mutations.

We expose three unauthenticated POST endpoints — register, login,
and the public sign-up — each of which can be hammered to inflate
DB rows, brute-force credentials, or burn email budget. ``slowapi``
wraps starlette/FastAPI with Flask-Limiter-style decorators.

Limits are deliberately generous for legitimate use (a real human
clicking a sign-up form once at an event) but tight enough that an
attacker can't spin up thousands of inserts. Tighten in the
deployment env via ``RATE_LIMIT_*`` overrides if needed.

Storage is in-process by default. Each uvicorn worker then keeps its
own counters, so the real budget is the configured limit times the
number of workers, and every deploy resets it. Set
``RATE_LIMIT_STORAGE_URI`` to a Redis URL in production and all workers
share one set of counters; slowapi uses it as soon as it is set.
``docs/deploy.md`` has the Coolify steps.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import settings


def _key_func(request) -> str:  # type: ignore[no-untyped-def]
    """Per-IP key. Behind a reverse proxy that sets
    ``X-Forwarded-For``, slowapi's ``get_remote_address`` reads it
    only when ``app.state.limiter`` is told to trust the header.
    For now we rely on the proxy stripping spoofed values."""
    return get_remote_address(request)


# The fallback budget for any request that does not carry its own
# ``@limiter.limit``. That is every read: the public pages, the
# organiser app's GETs, and each static asset the SPA fetches, because
# the limiter counts requests and not page views.
#
# It was 120 a minute, which sounds generous and is not. Loading one
# public page costs the HTML plus a dozen hashed assets, so 120
# requests is about eight page views, and everyone behind one office,
# school or mobile-carrier address shares a single budget. Measured on
# production: 130 requests to a chapter agenda returned 120 OK and 10
# rejections, with the server otherwise idle.
#
# 600 a minute is ten requests a second per address: around forty page
# views a minute for one visitor, or a small office browsing normally,
# while still stopping a script that loops. The endpoints worth
# protecting are protected by name in ``Limits`` below, and
# ``tests/test_rate_limits_audit.py`` fails if a new mutating route
# forgets one.
_DEFAULT_LIMIT = "600/minute"

limiter = Limiter(
    key_func=_key_func,
    storage_uri=settings.rate_limit_storage_uri,
    default_limits=[_DEFAULT_LIMIT],
)


# Named per-class limits. Routers should pull from this class
# rather than hard-coding ``"60/hour"`` literals — same intent,
# one place to tune. Keep numbers consistent with
# ``docs/architecture.md`` § Rate limiting.
class Limits:
    # Anonymous public surfaces — an attacker can spin these up
    # without any auth gate. Tightest budgets.
    AUTH = "5/hour"  # /auth/login-link (per IP)
    LOGIN_REDEEM = "20/minute"  # /auth/login (token redemption)
    PUBLIC_SIGNUP = "30/hour"  # /events/by-slug/{slug}/signups
    PUBLIC_SUBMIT = "20/hour"  # public questionnaire submits: /feedback/{token}/submit + /forms/by-slug/{slug}/submit
    # ``/start/*``: creates an account as a side effect, so it is the
    # tightest budget on the app. A person making one event needs it
    # once or twice; anything above that is somebody minting accounts.
    PUBLIC_WRITE = "5/hour"

    # Authenticated routine writes — comfortable for normal use,
    # bounds runaway scripts. Used for PATCH/PUT, admin
    # promote/demote/approve, event update.
    ORG_WRITE = "60/hour"

    # Authenticated rare actions — chapter mutations, event create
    # / archive / restore, user delete. Lower budget than ORG_WRITE
    # both because they're rarer and because each one's blast
    # radius is bigger.
    ORG_RARE = "30/hour"

    # Expensive: actually sends emails. Per-event manual trigger.
    SEND_EMAILS_NOW = "5/hour"
