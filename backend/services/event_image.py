"""Event-image upload pipeline.

Two-stage flow: the organiser POSTs a file, ``process_upload``
turns whatever they sent into a single canonical 4:5 JPEG (the
Instagram-portrait ratio organisers' flyers are usually designed
to), and ``upload_to_github`` PUTs it to the configured GitHub
repo via the Contents API. The returned ``raw.githubusercontent.com``
URL is what gets stored on ``Event.image_url`` — never the GitHub
``contents`` API URL, which would 404 anonymously and rate-limit
on heavy load.

Why GitHub: the deployment server is RAM-constrained and we
don't want to operate object storage. Public GitHub repos are
CDN-fronted for free and rate-limited generously. The PAT in
env has ``contents: write`` on a single repo so a leak's
blast radius is bounded to that repo's history.

The image is rewritten end-to-end before upload:

* EXIF rotation is applied and the EXIF block is dropped — phones
  routinely upload images "rotated" in EXIF only, which renders
  sideways in email clients that don't honour the tag.
* Center-cropped to 4:5, then resized to 1200x1500 — single
  source of truth for every consumer (public sign-up page caps
  display height; emails embed at 544px wide; OG cards inherit
  the original).
* JPEG q=85, ``optimize=True``. Strips alpha (flattens onto
  white) and any colour profile that isn't sRGB so email
  clients don't render shifted hues.

Old files stay in the repo forever — the lifecycle answer in
the plan was "leave it". Replacing an event's image overwrites
``event.image_url`` with the new path; the prior commit is the
audit log.
"""

import base64
import io
from typing import Final

import httpx
import structlog
from PIL import Image, ImageOps

from ..config import settings

logger = structlog.get_logger()

# Output dimensions. 4:5 portrait at 1200x1500 covers retina
# rendering at 600x750 (twice the SPA card width) and gives email
# clients a crisp 544x680 display when the template caps width to
# the email card's inner content area. 4:5 matches Instagram's
# portrait-post crop, which is what organisers' flyers are
# usually laid out for.
_OUT_W: Final[int] = 1200
_OUT_H: Final[int] = 1500

# Maximum upload payload. Bigger than any phone photo, smaller
# than anything that would OOM Pillow on the 1 GB container.
MAX_UPLOAD_BYTES: Final[int] = 8 * 1024 * 1024  # 8 MiB

# JPEG encode quality. 85 is the standard "indistinguishable from
# the source at typical viewing sizes" sweet spot; q=95 doubles
# file size for no perceptible gain.
_JPEG_QUALITY: Final[int] = 85


class ImageProcessingError(ValueError):
    """Raised when the upload isn't a usable image. The router
    surfaces this as a 400 with the message — the organiser sees
    "Not a valid image", not a stack trace."""


class GithubUploadError(RuntimeError):
    """Raised when the GitHub Contents API call fails. The router
    surfaces this as a 502 — distinguishes a transient upstream
    blip from a 4xx caused by what the organiser uploaded."""


def process_upload(data: bytes) -> bytes:
    """Validate, normalise, and re-encode the upload to a
    canonical 1200x1500 4:5 sRGB JPEG. Raises ``ImageProcessingError``
    on anything that isn't a usable image; the resulting bytes
    are safe to ship straight to GitHub."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageProcessingError(f"Image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB")
    if not data:
        raise ImageProcessingError("Empty upload")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001  — Pillow raises a zoo of unrelated types
        raise ImageProcessingError("Not a valid image") from exc

    # EXIF-aware rotate before any geometry math.
    img = ImageOps.exif_transpose(img)

    # Flatten to RGB on white — JPEG has no alpha channel; without
    # this transparent PNG uploads would crash the encoder. White
    # matches the email card and public-page card backgrounds.
    if img.mode != "RGB":
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background

    # Center-crop to 4:5 (no letterboxing), then resize to target.
    # ``fit`` picks the largest 4:5 rectangle inside the source and
    # resamples it to 1200x1500 — upscaling if the source is smaller
    # on either axis. LANCZOS + JPEG q=85 hides upscale fuzz well
    # enough at hero-card size, and rejecting small images just
    # leaves the organiser staring at a 400 they can't act on.
    img = ImageOps.fit(img, (_OUT_W, _OUT_H), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def _raw_url(owner: str, repo: str, branch: str, path: str) -> str:
    """The raw.githubusercontent.com URL that ``contents`` API
    upload results in. Built independently of the API response
    so we don't depend on GitHub's ``download_url`` field shape."""
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def upload_to_github(
    *,
    event_id: str,
    timestamp_ms: int,
    jpeg_bytes: bytes,
) -> str:
    """PUT the JPEG to the configured repo via the Contents API
    and return the public ``raw.githubusercontent.com`` URL.

    ``timestamp_ms`` is the unique-ifier inside the per-event
    directory; the caller mints it (``services.events.now_wallclock``
    -derived) so the workflow stays deterministic in tests.

    Raises ``GithubUploadError`` on any non-2xx response."""
    if not settings.event_images_enabled:
        raise GithubUploadError("Event-image storage is not configured")

    owner = settings.github_images_repo_owner
    repo = settings.github_images_repo_name
    branch = settings.github_images_branch
    token = settings.github_images_token

    # Mypy guard — ``event_images_enabled`` already proved these
    # aren't None, but the linter can't follow it through the
    # boolean.
    assert owner is not None and repo is not None and token is not None

    path = f"events/{event_id}/{timestamp_ms}.jpg"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    body = {
        "message": f"event {event_id}: image upload",
        "content": base64.b64encode(jpeg_bytes).decode("ascii"),
        "branch": branch,
    }
    headers = {
        "Authorization": f"Bearer {token.get_secret_value()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        resp = httpx.put(api_url, json=body, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        logger.warning("event_image_upload_network_error", error=str(exc))
        raise GithubUploadError("Upload to GitHub failed") from exc

    if resp.status_code not in (200, 201):
        logger.warning(
            "event_image_upload_failed",
            status=resp.status_code,
            body=resp.text[:500],
        )
        raise GithubUploadError(f"GitHub Contents API returned {resp.status_code}")

    return _raw_url(owner, repo, branch, path)
