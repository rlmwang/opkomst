"""Audit: every mutating endpoint has a rate limit.

Iterates the FastAPI app routes and asserts that every
POST / PATCH / PUT / DELETE under ``/api/v1/`` has a
``@limiter.limit(...)`` decorator. A new endpoint added
without a limit fails this test, which is faster to localise
than discovering the gap during a load incident.

Exemptions are explicit (``_EXEMPT``) — the ``send-emails-now``
trigger is already limited via the dispatcher's per-event
budget, etc.
"""

from fastapi import FastAPI
from fastapi.routing import APIRoute

from backend.main import app

_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Routes deliberately not gated at the request layer. Document
# *why* — the audit test reads this comment.
_EXEMPT: set[tuple[str, str]] = set()


def _route_has_limit(route: APIRoute) -> bool:
    """slowapi attaches its tracker to the endpoint via the
    ``__wrapped__`` chain when the decorator is applied. We can't
    introspect the limit string itself but we can detect
    decoration: rate-limited handlers carry an injected attribute
    or the decorator has stored metadata in
    ``app.state.limiter._marked_for_limiting`` / route extras.

    The reliable signal is the function's qualified name appearing
    in the slowapi limiter registry."""
    from backend.services.rate_limit import limiter

    func = route.endpoint
    qual = getattr(func, "__qualname__", "")
    # ``Limiter`` records every decorated function in
    # ``_route_limits`` keyed by the wrapped callable's name.
    return any(qual in str(k) for k in limiter._route_limits)


def test_every_mutating_endpoint_is_rate_limited() -> None:
    assert isinstance(app, FastAPI)
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1/"):
            continue
        methods = (route.methods or set()) & _MUTATING_METHODS
        if not methods:
            continue
        for method in methods:
            if (method, route.path) in _EXEMPT:
                continue
            if not _route_has_limit(route):
                missing.append(f"{method} {route.path}")
    assert not missing, (
        "rate-limit gap detected — add @limiter.limit(...) to:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )
