"""``/ads.txt`` and ``/robots.txt``: the two files a crawler asks for.

Both are text served from the root, both would otherwise be answered by
the SPA fallback with the app's HTML shell, and both are read by
machines that quietly draw the wrong conclusion from that rather than
erroring. They share a module for that reason.

``/ads.txt``: who is allowed to sell this site's inventory.

The IAB file every programmatic buyer checks before bidding. It names
the ad systems authorised to sell for this domain, and a buyer that
cannot find its seller listed treats the inventory as unauthorised. It
is also one of the ways AdSense verifies that the account and the site
belong to the same person.

Served from the environment rather than committed as a static file, for
the same reason nothing else about advertising is committed: a
deployment with no ``ADSENSE_CLIENT_ID`` authorises nobody, and says so
with a 404 rather than by publishing an empty file or somebody else's
publisher id.

The route is registered before the SPA fallback, or ``/ads.txt`` would
answer with the app's HTML shell and a crawler would read that as a
malformed file (see ``routers/spa.py``).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from ..config import settings

router = APIRouter(tags=["crawlers"], include_in_schema=False)

# Nothing here is secret, and the pages worth indexing are the public
# ones. What a crawler should not spend its budget on is the organiser
# app behind a login, the per-submission edit links, or the API. The
# edit links matter most: they carry a secret token in the URL, and a
# crawler that follows one out of a referrer header would put it in an
# index.
_ROBOTS = """User-agent: *
Disallow: /api/
Disallow: /auth/
Disallow: /admin/
Disallow: /register/
Allow: /
"""

# The one relationship this site has: a direct account with Google, and
# their certification-authority id, which is a fixed constant every
# AdSense publisher declares.
_GOOGLE_ADSYSTEM = "google.com"
_GOOGLE_CERTIFICATION_AUTHORITY = "f08c47fec0942fa0"


def _publisher_id() -> str | None:
    """The ``pub-…`` form of the client id. The ad tag wants it prefixed
    with ``ca-``; ads.txt wants it without, and a file carrying the
    prefix is the single most common reason a publisher id reads as
    missing."""
    raw = settings.adsense_client_id
    if not raw:
        return None
    return raw.removeprefix("ca-")


@router.head("/robots.txt", include_in_schema=False)
@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> PlainTextResponse:
    """What a crawler may walk. Without this the SPA fallback answers
    with an HTML page, which a crawler parses as an unusable file and
    treats as no rules at all: the right outcome by accident, from a
    response that says nothing anyone meant."""
    return PlainTextResponse(_ROBOTS, headers={"Cache-Control": "public, max-age=3600"})


@router.head("/ads.txt", include_in_schema=False)
@router.get("/ads.txt", response_class=PlainTextResponse)
def ads_txt() -> PlainTextResponse:
    """Authorised sellers for this domain, or a 404 when there are
    none. An empty file would be a claim that nobody is authorised,
    which is a different statement from having nothing to declare."""
    publisher = _publisher_id()
    if publisher is None:
        raise HTTPException(status_code=404, detail="Not found")
    line = f"{_GOOGLE_ADSYSTEM}, {publisher}, DIRECT, {_GOOGLE_CERTIFICATION_AUTHORITY}"
    return PlainTextResponse(
        line + "\n",
        headers={"Cache-Control": "public, max-age=3600"},
    )
