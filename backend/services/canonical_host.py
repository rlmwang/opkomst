"""One hostname, and a permanent redirect from the other.

``www.opkomst.nu`` and ``opkomst.nu`` resolve to the same server and,
without this, both serve the site. That splits every link anyone makes
between two hostnames: two entries in a search index, two sets of
signals, and a canonical tag doing work a redirect should have done.

The apex is the canonical host because it is what ``PUBLIC_BASE_URL``
names, which is what every canonical tag, sitemap entry and emailed
link already says. This middleware makes the server agree with them.

Only the ``www.`` form redirects, and only to the configured host. A
request arriving on any other hostname is left alone: that is a proxy
or a health check calling by container name or IP, and answering it
with a redirect to somewhere else would break it.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from ..config import settings


class CanonicalHostMiddleware(BaseHTTPMiddleware):
    """``https://www.example.com/x?y`` → ``https://example.com/x?y``,
    301, path and query kept."""

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._canonical = str(settings.public_base_url).rstrip("/")
        # The hostname alone: the Host header carries a port in dev and
        # none in production, and the comparison is about which name was
        # asked for, not which socket answered.
        self._host = self._canonical.split("://", 1)[-1].split(":", 1)[0]

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        host = request.headers.get("host", "").split(":", 1)[0]
        if host == f"www.{self._host}":
            target = self._canonical + request.url.path
            if request.url.query:
                target = f"{target}?{request.url.query}"
            # 301 rather than 302: this is not a decision that changes
            # later, and a permanent redirect is what moves the ranking
            # signals across instead of leaving them on the old host.
            return RedirectResponse(target, status_code=301)
        response: Response = await call_next(request)
        return response
