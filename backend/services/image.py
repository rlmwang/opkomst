"""Shared image-upload pipeline (events, forms, datepolls).

Two-stage flow: the organiser POSTs a file, ``process_upload`` turns
whatever they sent into a single canonical 4:5 JPEG (the Instagram-
portrait ratio organisers' flyers are usually designed to), and
``upload_to_github`` PUTs it to the configured GitHub repo via the
Contents API under a per-resource folder. The returned
``raw.githubusercontent.com`` URL is what gets stored on the row's
``image_url`` — never the GitHub ``contents`` API URL, which would
404 anonymously and rate-limit on heavy load.

Why GitHub: the deployment server is RAM-constrained and we don't
want to operate object storage. Public GitHub repos are CDN-fronted
for free and rate-limited generously. The PAT in env has
``contents: write`` on a single repo so a leak's blast radius is
bounded to that repo's history.

The image is rewritten end-to-end before upload:

* EXIF rotation is applied and the EXIF block is dropped — phones
  routinely upload images "rotated" in EXIF only, which renders
  sideways in email clients that don't honour the tag.
* Center-cropped to 4:5, then resized to 1200x1500 — single source of
  truth for every consumer.
* JPEG q=85, ``optimize=True``. Strips alpha (flattens onto white)
  and any colour profile that isn't sRGB.

Old files stay in the repo forever — the lifecycle answer is "leave
it". Replacing a row's image overwrites ``image_url``; the prior
commit is the audit log.
"""

import base64
import io
from typing import Final

import httpx
import structlog
from PIL import Image, ImageOps

from ..config import settings

logger = structlog.get_logger()

# Output dimensions — 4:5 portrait at 1200x1500. Covers retina at
# 600x750 and gives email clients a crisp 544x680 display.
_OUT_W: Final[int] = 1200
_OUT_H: Final[int] = 1500

# Maximum upload payload. Bigger than any phone photo, smaller than
# anything that would OOM Pillow on the 1 GB container.
MAX_UPLOAD_BYTES: Final[int] = 8 * 1024 * 1024  # 8 MiB

_JPEG_QUALITY: Final[int] = 85


class ImageProcessingError(ValueError):
    """Raised when the upload isn't a usable image. The router
    surfaces this as a 400 with the message."""


class GithubUploadError(RuntimeError):
    """Raised when the GitHub Contents API call fails. The router
    surfaces this as a 502."""


def process_upload(data: bytes) -> bytes:
    """Validate, normalise, and re-encode the upload to a canonical
    1200x1500 4:5 sRGB JPEG. Raises ``ImageProcessingError`` on
    anything that isn't a usable image."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageProcessingError(f"Image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB")
    if not data:
        raise ImageProcessingError("Empty upload")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001  — Pillow raises a zoo of unrelated types
        raise ImageProcessingError("Not a valid image") from exc

    img = ImageOps.exif_transpose(img)

    if img.mode != "RGB":
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background

    img = ImageOps.fit(img, (_OUT_W, _OUT_H), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def _raw_url(owner: str, repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def upload_to_github(
    *,
    folder: str,
    entity_id: str,
    timestamp_ms: int,
    jpeg_bytes: bytes,
) -> str:
    """PUT the JPEG to the configured repo via the Contents API and
    return the public ``raw.githubusercontent.com`` URL. ``folder`` is
    the per-resource directory (``events`` / ``forms`` / ``datepolls``);
    ``timestamp_ms`` is the unique-ifier inside the per-entity
    directory, minted by the caller so the workflow stays
    deterministic in tests.

    Raises ``GithubUploadError`` on any non-2xx response."""
    if not settings.event_images_enabled:
        raise GithubUploadError("Image storage is not configured")

    owner = settings.github_images_repo_owner
    repo = settings.github_images_repo_name
    branch = settings.github_images_branch
    token = settings.github_images_token

    # ``event_images_enabled`` already proved these aren't None.
    assert owner is not None and repo is not None and token is not None

    path = f"{folder}/{entity_id}/{timestamp_ms}.jpg"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    body = {
        "message": f"{folder} {entity_id}: image upload",
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
        logger.warning("image_upload_network_error", error=str(exc))
        raise GithubUploadError("Upload to GitHub failed") from exc

    if resp.status_code not in (200, 201):
        logger.warning("image_upload_failed", status=resp.status_code, body=resp.text[:500])
        raise GithubUploadError(f"GitHub Contents API returned {resp.status_code}")

    return _raw_url(owner, repo, branch, path)


def replace_entity_image(*, folder: str, entity_id: str, raw: bytes, timestamp_ms: int) -> str:
    """Process raw upload bytes and push to GitHub, returning the
    public URL. The two error types propagate so the router can map
    them to 400 (bad upload) vs 502 (upstream)."""
    jpeg = process_upload(raw)
    return upload_to_github(folder=folder, entity_id=entity_id, timestamp_ms=timestamp_ms, jpeg_bytes=jpeg)
