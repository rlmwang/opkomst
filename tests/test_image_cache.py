"""The read cache and the card variant.

Without a CDN in front, every visitor's request for a picture used to
become a fresh HTTPS connection to the storage host and ~900 KB back
through this box. Two things these tests pin:

* a stored path names one file for ever, so bytes fetched once can be
  served from disk afterwards, and the cache needs no invalidation;
* the card variant is made from the full one, so every picture already
  stored has a small version without anything being re-uploaded.
"""

import io
from typing import Any

import pytest
from PIL import Image

from backend.services import image as image_svc


@pytest.fixture()
def cache_dir(tmp_path: Any, monkeypatch: Any):
    """Point the cache at a temp directory for the duration of a test.

    ``_cache_dir`` rather than the setting: ``Settings`` is frozen, which
    is the point of it (``backend/config.py``)."""
    monkeypatch.setattr(image_svc, "_cache_dir", lambda: tmp_path)
    return tmp_path


def _jpeg(width: int = 1200, height: int = 1500) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(out, format="JPEG", quality=85)
    return out.getvalue()


_PATH = "events/019de066-e5a0-7c72-b8f0-19ac82f692b2/1780756211290.jpg"


def test_a_fetched_image_is_only_fetched_once(cache_dir: Any, monkeypatch: Any) -> None:
    calls: list[str] = []
    payload = _jpeg()

    class _Resp:
        status_code = 200
        content = payload

    def _get(url: str, **_: Any) -> Any:
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(image_svc.httpx, "get", _get)
    monkeypatch.setattr(image_svc, "_config", lambda: ("o", "r", "main", "t"))

    assert image_svc.fetch(_PATH) == payload
    assert image_svc.fetch(_PATH) == payload
    assert len(calls) == 1, "the second read should come from the cache"


def test_the_card_is_smaller_than_the_full_picture(cache_dir: Any, monkeypatch: Any) -> None:
    payload = _jpeg()
    monkeypatch.setattr(image_svc, "fetch", lambda path: payload)

    card = image_svc.card_bytes(_PATH)

    assert card is not None
    with Image.open(io.BytesIO(card)) as img:
        assert img.size == (image_svc._CARD_W, image_svc._CARD_H)
    assert len(card) < len(payload)


def test_the_card_is_rendered_once(cache_dir: Any, monkeypatch: Any) -> None:
    payload = _jpeg()
    fetches: list[str] = []

    def _fetch(path: str) -> bytes:
        fetches.append(path)
        return payload

    monkeypatch.setattr(image_svc, "fetch", _fetch)

    first = image_svc.card_bytes(_PATH)
    second = image_svc.card_bytes(_PATH)

    assert first == second
    assert len(fetches) == 1, "the second card should come from the cache"


def test_a_missing_image_has_no_card(cache_dir: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(image_svc, "fetch", lambda path: None)
    assert image_svc.card_bytes(_PATH) is None


def test_caching_off_still_serves(monkeypatch: Any) -> None:
    """A dev machine has no volume, and a broken cache must never stop a
    picture being served."""
    monkeypatch.setattr(image_svc, "_cache_dir", lambda: None)
    payload = _jpeg()

    class _Resp:
        status_code = 200
        content = payload

    monkeypatch.setattr(image_svc.httpx, "get", lambda url, **_: _Resp())
    monkeypatch.setattr(image_svc, "_config", lambda: ("o", "r", "main", "t"))

    assert image_svc.fetch(_PATH) == payload


def test_the_sweep_drops_the_least_recently_read(cache_dir: Any, monkeypatch: Any) -> None:
    """The bound is on disk, not on count: a cache that grows without
    limit shares a volume with the backups."""
    monkeypatch.setattr(image_svc, "_CACHE_MAX_BYTES", 4096)
    for i in range(6):
        image_svc._cache_write(f"events/x/{i}.jpg", "full", b"\x00" * 2048)

    remaining = list(cache_dir.glob("*.jpg"))
    assert remaining, "the sweep should not empty the cache"
    assert sum(f.stat().st_size for f in remaining) <= 4096
