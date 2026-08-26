"""One hostname serves the site; the other says where it went.

``www.opkomst.nu`` and the apex resolve to the same server, so without a
redirect both serve every page and every link anyone makes is split
between two hostnames. The canonical tags, the sitemap and the emailed
links all name the apex already; this is the server agreeing with them.
"""

from __future__ import annotations

from backend.config import settings

_HOST = str(settings.public_base_url).rstrip("/").split("://", 1)[-1]


def test_www_redirects_permanently_to_the_apex(client) -> None:
    """301, not 302: the ranking signals only move across on a
    permanent one."""
    response = client.get("/", headers={"host": f"www.{_HOST}"}, follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == str(settings.public_base_url).rstrip("/") + "/"


def test_the_redirect_keeps_the_path_and_the_query(client) -> None:
    """A link to a page has to land on that page. Dropping the path
    would send every inbound www link to the front door, which is worse
    than the split it is fixing."""
    response = client.get(
        "/datumprikker-zonder-account?utm_source=x",
        headers={"host": f"www.{_HOST}"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"].endswith("/datumprikker-zonder-account?utm_source=x")


def test_the_apex_is_served_rather_than_redirected(client) -> None:
    """The obvious way to get this wrong is a loop."""
    assert client.get("/", headers={"host": _HOST}).status_code == 200


def test_another_hostname_is_left_alone(client) -> None:
    """Coolify's health check and the container network call this
    server by names that are not the public one. A redirect to the
    public host would send them somewhere they cannot reach."""
    assert client.get("/health", headers={"host": "opkomst-api.internal"}).status_code == 200
