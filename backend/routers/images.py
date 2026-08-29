"""Hero images, served from this app's own domain.

``GET /i/{path}`` is the URL any page, link preview or email carries for
an uploaded image, and ``GET /i/card/{path}`` is the same picture at
600x750 for the places that show it small. It reads the file from wherever the
storage happens to be (``services/image.py``) and answers with the
JPEG, so nothing rendered anywhere names the host that keeps the bytes.

The path already identifies one specific file for ever: uploads land at
``{kind}/{entity id}/{timestamp}.jpg`` and a replacement gets a new
timestamp, so the response is immutable and cacheable for a year.
Cloudflare and the browser then serve almost all of it and the origin
sees each image about once.

No authentication: these are the pictures on public event pages. The
route is deliberately dumb about what a path means, and refuses
anything that isn't the shape uploads produce.
"""

import re
from typing import Final

import structlog
from fastapi import APIRouter, HTTPException, Response

from ..services import image as image_svc

logger = structlog.get_logger()

router = APIRouter(tags=["images"], include_in_schema=False)

# What an upload produces and nothing else: two path segments and a
# timestamped ``.jpg``. Keeps traversal, absolute URLs and any attempt
# to fetch something else out of the storage host away from ``fetch``.
_PATH_RE: Final[re.Pattern[str]] = re.compile(r"^(events|forms|datepolls|chores)/[A-Za-z0-9_-]{1,64}/\d{10,20}\.jpg$")

# A year, immutable: the URL names one file that never changes.
_CACHE: Final[str] = "public, max-age=31536000, immutable"


@router.get("/i/card/{path:path}")
def serve_card_image(path: str) -> Response:
    """The same picture at 600x750, for the places that show it small.

    An agenda card gives the poster about 200 px. Sending the full
    1200x1500 for that is twenty times the bytes the page needs, and
    without a CDN every one of them comes off this host. The variant is
    made once from the full file and cached beside it.

    Its own path rather than a query parameter: the URL still names one
    immutable thing, so it stays cacheable for a year by anything that
    caches at all. Declared before ``/i/{path}`` so it wins the match —
    that route would take ``card/event/…`` and refuse it.
    """
    if not _PATH_RE.match(path):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        data = image_svc.card_bytes(path)
    except image_svc.GithubUploadError:
        raise HTTPException(status_code=502, detail="Image is temporarily unavailable") from None
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": _CACHE})


@router.get("/i/{path:path}")
def serve_image(path: str) -> Response:
    if not _PATH_RE.match(path):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        data = image_svc.fetch(path)
    except image_svc.GithubUploadError:
        # Never the upstream's name or URL, here or in the log line
        # above it: the point of this route is that nothing says where
        # the file lives.
        raise HTTPException(status_code=502, detail="Image is temporarily unavailable") from None

    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": _CACHE})
