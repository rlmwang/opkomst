"""Shared image pipeline: process, store, serve, delete.

The organiser POSTs a file, ``process_upload`` turns whatever they sent
into a single canonical 4:5 JPEG (the Instagram-portrait ratio
organisers' flyers are usually designed to), and ``store`` PUTs it to
the configured GitHub repo via the Contents API under a per-resource
folder. What the row keeps is the **path** it was stored at, never a
URL to it.

**Nothing the app renders says where the bytes live.** ``public_url``
builds ``{public base}/i/{path}``, and ``routers/images.py`` reads the
file back through ``fetch``. So a page, a link preview and an email all
point at this app, and the hosting account is not in any of them. The
repository itself is public, so this hides the hosting from everyone
reading what the app hands out, not from someone who finds the repo
another way.

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

**Everything here blocks, so every caller is a sync ``def``.**
``process_upload`` is Pillow decoding and re-encoding, and ``store``,
``fetch`` and ``delete`` are synchronous ``httpx`` calls with timeouts
up to 30 s. In an ``async def`` route that runs on the event loop and
stalls every other request the worker is serving, for the whole decode
plus however long the storage host takes to answer. A plain ``def``
route hands the same work to Starlette's threadpool, where one slow
upload costs one thread. The upload routes are ``def`` for that reason
and must stay that way.

Files are deleted when nothing points at them any more: when an image
is replaced, when it is removed, and when the entity holding it has
been archived long enough (``services/image_reaper.py``). A delete
removes the file from the repository's current tree; the blob stays in
its history, which is the accepted cost of storing images in git.

**Reads are cached on disk, and cards are smaller.** Without a CDN in
front, every visitor's request for a picture used to become a fresh
HTTPS connection to the storage host and ~900 KB back through this box.
Two things fix most of that:

* ``fetch`` writes what it reads into ``IMAGE_CACHE_DIR`` and serves
  from there afterwards. A stored path names one file for ever — a
  replacement gets a new timestamp — so a cached file can never be
  stale, and the cache needs no invalidation, only a size bound.
* ``card_bytes`` is the same picture at 600x750, made once from the
  full one and cached beside it. An agenda card shows the poster about
  200 px wide; sending 1200x1500 for that is twenty times the bytes the
  page needs, on the slowest connection the visitor has.
"""

import base64
import hashlib
import io
import pathlib
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

# The card variant: half the full size in each direction, which is still
# retina for the ~200 px slot an agenda card gives it.
_CARD_W: Final[int] = 600
_CARD_H: Final[int] = 750
_CARD_QUALITY: Final[int] = 80

# How much disk the read cache may take before the oldest files are
# dropped. Sized to hold a few hundred pictures — far more than a
# chapter has — while leaving the volume to the backups it shares.
_CACHE_MAX_BYTES: Final[int] = 512 * 1024 * 1024


def _cache_dir() -> pathlib.Path | None:
    """Where fetched bytes are kept, or ``None`` when caching is off.

    Off is a legitimate state: a dev machine has no volume, and a broken
    cache must never stop an image being served."""
    configured = settings.image_cache_dir
    if not configured:
        return None
    try:
        path = pathlib.Path(configured)
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError as exc:
        logger.warning("image_cache_unavailable", error=str(exc))
        return None


def _cache_name(path: str, variant: str) -> str:
    """A flat filename for a stored path. Hashed rather than nested so
    the cache is one directory that can be swept by mtime, and so a
    path can never escape it."""
    digest = hashlib.sha256(f"{variant}:{path}".encode()).hexdigest()
    return f"{digest}.jpg"


def _cache_read(path: str, variant: str) -> bytes | None:
    directory = _cache_dir()
    if directory is None:
        return None
    file = directory / _cache_name(path, variant)
    try:
        data = file.read_bytes()
    except OSError:
        return None
    # Touch on read so the sweep drops what nobody looks at, rather than
    # what happens to be old.
    try:
        file.touch()
    except OSError:
        pass
    return data


def _cache_write(path: str, variant: str, data: bytes) -> None:
    directory = _cache_dir()
    if directory is None:
        return
    file = directory / _cache_name(path, variant)
    try:
        # Written beside and renamed: a reader never sees half a file.
        temporary = file.with_suffix(".part")
        temporary.write_bytes(data)
        temporary.replace(file)
    except OSError as exc:
        logger.warning("image_cache_write_failed", error=str(exc))
        return
    _sweep(directory)


def _sweep(directory: pathlib.Path) -> None:
    """Drop the least recently read files once the cache is over its
    bound. Cheap enough to run on write: the cache holds hundreds of
    files, not millions."""
    try:
        files = [(f, f.stat()) for f in directory.glob("*.jpg")]
    except OSError:
        return
    total = sum(stat.st_size for _, stat in files)
    if total <= _CACHE_MAX_BYTES:
        return
    for file, stat in sorted(files, key=lambda pair: pair[1].st_atime):
        try:
            file.unlink()
        except OSError:
            continue
        total -= stat.st_size
        if total <= _CACHE_MAX_BYTES:
            return


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


def public_url(path: str | None) -> str | None:
    """The URL to hand to a page, a link preview or an email.

    Absolute, because mail clients and Open Graph scrapers can't resolve
    a relative one, and always this app's own host. ``None`` in, ``None``
    out, so a DTO can pass a nullable column straight through."""
    if not path:
        return None
    return f"{str(settings.public_base_url).rstrip('/')}/i/{path.lstrip('/')}"


def card_url(path: str | None) -> str | None:
    """The URL for the small version, for a page that shows the picture
    in a card rather than as a hero."""
    if not path:
        return None
    return f"{str(settings.public_base_url).rstrip('/')}/i/card/{path.lstrip('/')}"


def _config() -> tuple[str, str, str, str]:
    """``(owner, repo, branch, token)``, or raise if the storage isn't
    configured. One place asserts it so the callers below read as
    straight-line code."""
    if not settings.event_images_enabled:
        raise GithubUploadError("Image storage is not configured")
    owner = settings.github_images_repo_owner
    repo = settings.github_images_repo_name
    token = settings.github_images_token
    # ``event_images_enabled`` already proved these aren't None.
    assert owner is not None and repo is not None and token is not None
    return owner, repo, settings.github_images_branch, token.get_secret_value()


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def store(*, folder: str, entity_id: str, timestamp_ms: int, jpeg_bytes: bytes) -> str:
    """PUT the JPEG to the configured repo and return the path it was
    stored at. ``folder`` is the per-resource directory (``events`` /
    ``forms`` / ``datepolls`` / ``chores``); ``timestamp_ms`` is the
    unique-ifier inside the per-entity directory, minted by the caller
    so the workflow stays deterministic in tests.

    Raises ``GithubUploadError`` on any non-2xx response."""
    owner, repo, branch, token = _config()
    path = f"{folder}/{entity_id}/{timestamp_ms}.jpg"
    body = {
        "message": f"{folder} {entity_id}: image upload",
        "content": base64.b64encode(jpeg_bytes).decode("ascii"),
        "branch": branch,
    }

    try:
        resp = httpx.put(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            json=body,
            headers=_headers(token),
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("image_upload_network_error", error=str(exc))
        raise GithubUploadError("Upload failed") from exc

    if resp.status_code not in (200, 201):
        logger.warning("image_upload_failed", status=resp.status_code, body=resp.text[:500])
        raise GithubUploadError(f"Image storage returned {resp.status_code}")

    return path


def fetch(path: str) -> bytes | None:
    """The stored file, or ``None`` when there is no such path.

    Read from the raw host rather than the Contents API: it is the
    CDN-fronted one, it returns the bytes directly instead of base64 in
    JSON, and this runs on the request path. Raises
    ``GithubUploadError`` when the host itself is unreachable, which the
    route turns into a 502; a missing file is not an error here, it is a
    404."""
    cached = _cache_read(path, "full")
    if cached is not None:
        return cached

    owner, repo, branch, _token = _config()
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    try:
        resp = httpx.get(url, timeout=15.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.warning("image_fetch_network_error", error=str(exc))
        raise GithubUploadError("Image storage is unreachable") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning("image_fetch_failed", status=resp.status_code)
        raise GithubUploadError(f"Image storage returned {resp.status_code}")
    _cache_write(path, "full", resp.content)
    return resp.content


def card_bytes(path: str) -> bytes | None:
    """The same picture at 600x750, or ``None`` when there is no such
    path.

    Made from the full one the first time it is asked for and cached
    beside it, rather than written at upload: every picture already
    stored gets the smaller version too, and the storage host keeps one
    file per image instead of two that have to be deleted together.
    """
    cached = _cache_read(path, "card")
    if cached is not None:
        return cached
    full = fetch(path)
    if full is None:
        return None
    try:
        with Image.open(io.BytesIO(full)) as img:
            img = ImageOps.exif_transpose(img) or img
            img = img.convert("RGB")
            img = img.resize((_CARD_W, _CARD_H), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=_CARD_QUALITY, optimize=True, progressive=True)
    except OSError as exc:
        # A picture that cannot be resized is still a picture: serve the
        # full one rather than nothing.
        logger.warning("image_card_render_failed", error=str(exc))
        return full
    data = out.getvalue()
    _cache_write(path, "card", data)
    return data


def delete(path: str) -> bool:
    """Remove a stored file. True when it is gone (including when it was
    already gone), False when the host refused.

    Deleting through the Contents API needs the blob's sha, so this is a
    read then a delete. Never raises: every caller is cleaning up after
    something that has already happened, and a file that outlives its
    row costs storage, not correctness. The next sweep tries again."""
    owner, repo, branch, token = _config()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = _headers(token)

    try:
        head = httpx.get(api_url, params={"ref": branch}, headers=headers, timeout=15.0)
        if head.status_code == 404:
            return True
        if head.status_code != 200:
            logger.warning("image_delete_lookup_failed", status=head.status_code, path=path)
            return False
        sha = head.json().get("sha")
        if not isinstance(sha, str):
            logger.warning("image_delete_no_sha", path=path)
            return False
        resp = httpx.request(
            "DELETE",
            api_url,
            json={"message": f"remove {path}", "sha": sha, "branch": branch},
            headers=headers,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("image_delete_network_error", error=str(exc), path=path)
        return False

    if resp.status_code != 200:
        logger.warning("image_delete_failed", status=resp.status_code, path=path)
        return False
    logger.info("image_deleted", path=path)
    return True


def replace_entity_image(*, folder: str, entity_id: str, raw: bytes, timestamp_ms: int, previous: str | None) -> str:
    """Process the upload, store it, drop the file it replaces, and
    return the new path.

    The old file is deleted after the new one is stored, so a failed
    upload leaves the entity with the picture it had. The two error
    types propagate so the router can map them to 400 (bad upload) vs
    502 (upstream)."""
    jpeg = process_upload(raw)
    path = store(folder=folder, entity_id=entity_id, timestamp_ms=timestamp_ms, jpeg_bytes=jpeg)
    if previous and previous != path:
        delete(previous)
    return path
