"""``/i/{path}`` and the archived-image sweep.

The route is the whole point of storing a path instead of a URL: every
image a visitor, a link preview or a mail client asks for comes from
this app, and nothing anyone can see names the host that keeps the
bytes. The sweep is the other half: files stop existing when the thing
they belonged to has been archived long enough.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from _helpers import commit
from _helpers.events import make_event

from backend.models import Event
from backend.services import image as image_svc
from backend.services import image_reaper

_PATH = "events/ev1/1700000000000.jpg"
_JPEG = b"\xff\xd8\xffnot-really-a-jpeg"


# ---- The route ----------------------------------------------------


def test_serves_the_bytes_with_a_long_immutable_cache(client) -> None:
    """The URL names one file for ever (a replacement gets a new
    timestamp), so it is cacheable for a year and the origin sees each
    image about once."""
    with patch.object(image_svc, "fetch", return_value=_JPEG):
        r = client.get(f"/i/{_PATH}")
    assert r.status_code == 200
    assert r.content == _JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_says_nothing_about_where_the_file_is_kept(client) -> None:
    with patch.object(image_svc, "fetch", return_value=_JPEG):
        r = client.get(f"/i/{_PATH}")
    joined = " ".join(f"{k}: {v}" for k, v in r.headers.items())
    assert "github" not in joined.lower()


def test_a_missing_file_is_a_404(client) -> None:
    with patch.object(image_svc, "fetch", return_value=None):
        assert client.get(f"/i/{_PATH}").status_code == 404


def test_an_unreachable_store_is_a_502_that_names_nothing(client) -> None:
    with patch.object(image_svc, "fetch", side_effect=image_svc.GithubUploadError("raw.githubusercontent.com down")):
        r = client.get(f"/i/{_PATH}")
    assert r.status_code == 502
    assert "github" not in r.text.lower()


@pytest.mark.parametrize(
    "path",
    [
        # Not one of the four folders an upload writes to. (A ``..`` in
        # the URL is not among these: every HTTP client resolves it
        # before the request is sent, so it never reaches the route as
        # one.)
        "secrets/ev1/1700000000000.jpg",
        # Not the filename an upload writes.
        "events/ev1/1700000000000.png",
        "events/ev1/notatimestamp.jpg",
        "events/ev1/1.jpg",
        # Not two segments.
        "events/1700000000000.jpg",
        "events/ev1/nested/1700000000000.jpg",
        # An entity id an upload could never have produced.
        "events/ev 1/1700000000000.jpg",
        "events/ev1%2F../1700000000000.jpg",
    ],
)
def test_only_the_shape_an_upload_produces_is_served(client, path) -> None:
    """The route never gets to ask the store for anything but a file
    one of our own uploads wrote. Whatever a caller puts in the URL, the
    only thing that reaches the storage host is a path this app itself
    wrote earlier."""
    with patch.object(image_svc, "fetch", return_value=_JPEG) as fetched:
        r = client.get(f"/i/{path}")
    assert r.status_code == 404
    fetched.assert_not_called()


# ---- The sweep ----------------------------------------------------


def _archived(db, *, days_ago: int) -> Event:
    event = make_event(db)
    event.image_path = f"events/{event.id}/1.jpg"
    event.archived_at = datetime.now(UTC) - timedelta(days=days_ago)
    commit(db)
    return event


def test_deletes_the_image_of_something_archived_past_the_grace(db) -> None:
    event = _archived(db, days_ago=image_reaper.GRACE.days + 1)
    with patch.object(image_svc, "delete", return_value=True) as deleted:
        assert image_reaper.reap_images() == 1
    deleted.assert_called_once_with(f"events/{event.id}/1.jpg")
    db.refresh(event)
    assert event.image_path is None


def test_leaves_one_archived_inside_the_grace_alone(db) -> None:
    """Restoring is a normal thing to do, so a recent archive keeps its
    picture."""
    event = _archived(db, days_ago=image_reaper.GRACE.days - 1)
    with patch.object(image_svc, "delete", return_value=True) as deleted:
        assert image_reaper.reap_images() == 0
    deleted.assert_not_called()
    db.refresh(event)
    assert event.image_path is not None


def test_never_touches_a_live_entity(db) -> None:
    event = make_event(db)
    event.image_path = f"events/{event.id}/1.jpg"
    commit(db)
    with patch.object(image_svc, "delete", return_value=True) as deleted:
        assert image_reaper.reap_images() == 0
    deleted.assert_not_called()
    db.refresh(event)
    assert event.image_path is not None


def test_a_failed_delete_leaves_the_row_pointing_at_the_file(db) -> None:
    """Clearing the column first would strand the file for ever with
    nothing left that knows where it is. The next sweep retries."""
    event = _archived(db, days_ago=image_reaper.GRACE.days + 1)
    with patch.object(image_svc, "delete", return_value=False):
        assert image_reaper.reap_images() == 0
    db.refresh(event)
    assert event.image_path == f"events/{event.id}/1.jpg"
