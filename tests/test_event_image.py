"""Event-image pipeline: processing + GitHub upload + HTTP routes."""

import base64
import io
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from _helpers import commit
from PIL import Image
from pydantic import SecretStr

from backend.database import SessionLocal
from backend.models import Event
from backend.services import event_image

# --- process_upload --------------------------------------------------


def _png_bytes(w: int, h: int, mode: str = "RGB", color: tuple[int, ...] = (200, 50, 50)) -> bytes:
    """A real PNG of the requested dimensions. The pipeline rejects
    fake bytes, so the test inputs have to round-trip through
    Pillow themselves."""
    img = Image.new(mode, (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_process_upload_resizes_to_1200x900_jpeg() -> None:
    data = _png_bytes(3000, 2000)  # 3:2 source
    out = event_image.process_upload(data)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (1200, 900)


def test_process_upload_center_crops_to_4_3_aspect() -> None:
    data = _png_bytes(1920, 1080)  # 16:9 source
    out = event_image.process_upload(data)
    img = Image.open(io.BytesIO(out))
    assert img.size == (1200, 900)


def test_process_upload_flattens_alpha_onto_white() -> None:
    data = _png_bytes(1500, 1200, mode="RGBA", color=(0, 0, 0, 0))
    out = event_image.process_upload(data)
    img = Image.open(io.BytesIO(out))
    assert img.mode == "RGB"
    assert img.size == (1200, 900)
    assert img.getpixel((600, 450)) == (255, 255, 255)


def test_process_upload_rejects_too_large() -> None:
    too_big = b"\x00" * (event_image.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(event_image.ImageProcessingError, match="larger than"):
        event_image.process_upload(too_big)


def test_process_upload_rejects_non_image() -> None:
    with pytest.raises(event_image.ImageProcessingError, match="Not a valid image"):
        event_image.process_upload(b"this is not an image")


def test_process_upload_rejects_empty() -> None:
    with pytest.raises(event_image.ImageProcessingError, match="Empty"):
        event_image.process_upload(b"")


def test_process_upload_upscales_small_source() -> None:
    """Small sources are upscaled rather than rejected — an organiser
    with a sub-1200x900 flyer can still upload it. Output is always
    1200x900 4:3 JPEG."""
    from PIL import Image

    jpeg = event_image.process_upload(_png_bytes(800, 600))
    out = Image.open(io.BytesIO(jpeg))
    assert (out.width, out.height) == (1200, 900)
    assert out.format == "JPEG"


# --- upload_to_github ------------------------------------------------


@pytest.fixture()
def github_enabled():
    """Toggle the GitHub-storage config group on for the duration
    of one test. ``Settings`` is frozen, so we patch attribute
    access via ``object.__setattr__``."""
    import backend.config

    cfg = backend.config.settings
    saved = {
        "github_images_repo_owner": cfg.github_images_repo_owner,
        "github_images_repo_name": cfg.github_images_repo_name,
        "github_images_branch": cfg.github_images_branch,
        "github_images_token": cfg.github_images_token,
    }
    object.__setattr__(cfg, "github_images_repo_owner", "rlmwang")
    object.__setattr__(cfg, "github_images_repo_name", "opkomst-event-images")
    object.__setattr__(cfg, "github_images_branch", "main")
    object.__setattr__(cfg, "github_images_token", SecretStr("ghp_test"))
    try:
        yield
    finally:
        for k, v in saved.items():
            object.__setattr__(cfg, k, v)


def test_upload_to_github_puts_to_contents_api(github_enabled) -> None:
    captured: dict[str, Any] = {}

    def fake_put(url: str, json: dict, headers: dict, timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return httpx.Response(201, json={"content": {"sha": "abc"}})

    with patch.object(httpx, "put", side_effect=fake_put):
        url = event_image.upload_to_github(
            event_id="ev1",
            timestamp_ms=1700000000000,
            jpeg_bytes=b"\xff\xd8\xff",
        )

    assert url == (
        "https://raw.githubusercontent.com/rlmwang/opkomst-event-images/main/events/ev1/1700000000000.jpg"
    )
    assert captured["url"] == (
        "https://api.github.com/repos/rlmwang/opkomst-event-images/contents/events/ev1/1700000000000.jpg"
    )
    assert captured["headers"]["Authorization"] == "Bearer ghp_test"
    assert captured["json"]["branch"] == "main"
    assert base64.b64decode(captured["json"]["content"]) == b"\xff\xd8\xff"


def test_upload_to_github_raises_when_disabled() -> None:
    with pytest.raises(event_image.GithubUploadError, match="not configured"):
        event_image.upload_to_github(event_id="x", timestamp_ms=0, jpeg_bytes=b"j")


def test_upload_to_github_raises_on_non_2xx(github_enabled) -> None:
    def fake_put(url: str, json: dict, headers: dict, timeout: float) -> httpx.Response:
        return httpx.Response(422, text="bad payload")

    with patch.object(httpx, "put", side_effect=fake_put):
        with pytest.raises(event_image.GithubUploadError, match="422"):
            event_image.upload_to_github(event_id="ev1", timestamp_ms=1, jpeg_bytes=b"j")


def test_upload_to_github_raises_on_network_error(github_enabled) -> None:
    def fake_put(*a: Any, **kw: Any) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with patch.object(httpx, "put", side_effect=fake_put):
        with pytest.raises(event_image.GithubUploadError, match="failed"):
            event_image.upload_to_github(event_id="ev1", timestamp_ms=1, jpeg_bytes=b"j")


# --- HTTP routes -----------------------------------------------------


def _new_event(client: Any, headers: dict[str, str]) -> dict[str, Any]:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    chapter_id = me["chapters"][0]["id"]
    r = client.post(
        "/api/v1/events",
        headers=headers,
        json={
            "name": "Demo",
            "chapter_id": chapter_id,
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["Flyer"],
            "feedback_enabled": True,
            "reminder_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload(
    client: Any,
    headers: dict[str, str],
    event_id: str,
    file_bytes: bytes,
    filename: str = "photo.png",
    content_type: str = "image/png",
):
    return client.post(
        f"/api/v1/events/{event_id}/image",
        headers=headers,
        files={"file": (filename, file_bytes, content_type)},
    )


def test_upload_route_returns_503_when_storage_disabled(client, organiser_headers) -> None:
    e = _new_event(client, organiser_headers)
    r = _upload(client, organiser_headers, e["id"], _png_bytes(1500, 1200))
    assert r.status_code == 503


def test_upload_route_persists_url_and_returns_event(
    client, organiser_headers, github_enabled
) -> None:
    e = _new_event(client, organiser_headers)
    fake_url = "https://raw.githubusercontent.com/rlmwang/opkomst-event-images/main/events/x/1.jpg"
    with patch.object(event_image, "upload_to_github", return_value=fake_url):
        r = _upload(client, organiser_headers, e["id"], _png_bytes(1500, 1200))

    assert r.status_code == 200, r.text
    assert r.json()["image_url"] == fake_url

    fresh = SessionLocal()
    try:
        row = fresh.query(Event).filter_by(id=e["id"]).first()
        assert row is not None
        assert row.image_url == fake_url
    finally:
        fresh.close()


def test_upload_route_400s_on_bad_image(client, organiser_headers, github_enabled) -> None:
    e = _new_event(client, organiser_headers)
    r = _upload(client, organiser_headers, e["id"], b"not an image")
    assert r.status_code == 400


def test_upload_route_502s_on_github_failure(
    client, organiser_headers, github_enabled
) -> None:
    e = _new_event(client, organiser_headers)
    with patch.object(
        event_image,
        "upload_to_github",
        side_effect=event_image.GithubUploadError("simulated"),
    ):
        r = _upload(client, organiser_headers, e["id"], _png_bytes(1500, 1200))
    assert r.status_code == 502


def test_delete_route_clears_url(client, organiser_headers, db, github_enabled) -> None:
    e = _new_event(client, organiser_headers)
    row = db.query(Event).filter_by(id=e["id"]).first()
    assert row is not None
    row.image_url = "https://example.test/x.jpg"
    commit(db)

    r = client.delete(f"/api/v1/events/{e['id']}/image", headers=organiser_headers)
    assert r.status_code == 200
    assert r.json()["image_url"] is None


def test_delete_route_404s_when_no_image(client, organiser_headers) -> None:
    e = _new_event(client, organiser_headers)
    r = client.delete(f"/api/v1/events/{e['id']}/image", headers=organiser_headers)
    assert r.status_code == 404


# --- Email-render integration ---------------------------------------


def test_reminder_email_renders_img_tag_when_event_has_image_url(db, fake_email) -> None:
    """When ``event.image_url`` is set, the reminder body carries an
    ``<img>`` pointing at that URL. When it's null, no ``<img>``
    appears at all."""
    from datetime import timedelta

    from _helpers.events import make_event
    from _helpers.signups import make_signup

    from backend.models import EmailChannel
    from backend.services import mail_lifecycle
    from backend.services.events import now_wallclock

    starts_in = (now_wallclock() + timedelta(hours=24)) - now_wallclock()
    e = make_event(db, starts_in=starts_in)
    e.image_url = "https://raw.githubusercontent.com/rlmwang/opkomst-event-images/main/events/ev/1.jpg"
    make_signup(db, e, email="alice@example.org")
    commit(db)

    n = mail_lifecycle.run_once(EmailChannel.REMINDER)
    assert n == 1
    body = fake_email.sent[0].html_body
    assert e.image_url in body
    assert "<img" in body


def test_reminder_email_renders_artist_credit_when_handle_present(db, fake_email) -> None:
    """When both ``image_url`` and ``image_artist_instagram`` are
    set, the email body includes a credit line linking to the
    artist's Instagram. Without the handle, no credit line shows."""
    from datetime import timedelta

    from _helpers.events import make_event
    from _helpers.signups import make_signup

    from backend.models import EmailChannel
    from backend.services import mail_lifecycle
    from backend.services.events import now_wallclock

    starts_in = (now_wallclock() + timedelta(hours=24)) - now_wallclock()
    e = make_event(db, starts_in=starts_in)
    e.image_url = "https://example.test/x.jpg"
    e.image_artist_instagram = "rsp_amsterdam"
    make_signup(db, e, email="alice@example.org")
    commit(db)

    mail_lifecycle.run_once(EmailChannel.REMINDER)
    body = fake_email.sent[0].html_body
    assert "instagram.com/rsp_amsterdam" in body
    assert "@rsp_amsterdam" in body


def test_event_create_strips_leading_at_from_artist_handle(client, organiser_headers) -> None:
    """The schema validator normalises a pasted ``@handle`` to bare
    ``handle`` so URL construction is uniform."""
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "Demo",
            "chapter_id": me["chapters"][0]["id"],
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["Flyer"],
            "feedback_enabled": True,
            "reminder_enabled": True,
            "locale": "nl",
            "image_artist_instagram": "  @rsp_amsterdam ",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["image_artist_instagram"] == "rsp_amsterdam"


def test_event_create_rejects_invalid_instagram_handle(client, organiser_headers) -> None:
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "Demo",
            "chapter_id": me["chapters"][0]["id"],
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["Flyer"],
            "feedback_enabled": True,
            "reminder_enabled": True,
            "locale": "nl",
            "image_artist_instagram": "spaces not allowed",
        },
    )
    assert r.status_code == 422
    assert "instagram" in r.text.lower()
