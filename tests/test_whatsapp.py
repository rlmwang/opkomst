"""WhatsApp blast tool. proxy router and service tests.

Covers the contract:

* RBAC: admin-only on every route. Anon → 401, organiser → 403.
* Not-configured fallback: ``/status`` returns ``not_configured``,
  mutating routes return 503.
* Watchdog tear-down: a stale ``_last_seen`` + a connected
  Evolution session triggers ``delete_instance()`` on the next
  request.
* No PII in logs: the service module never logs ``number=`` /
  ``text=``. (Static grep. see ``test_no_pii_in_whatsapp_logs``.)

Evolution HTTP calls are mocked via ``respx`` so no test ever
touches the network.
"""

from __future__ import annotations

import datetime as _dt

import httpx
import pytest
import respx

# Importing the FastAPI app eagerly ensures ``backend.models`` is
# loaded so ``Base.metadata`` is populated by the time the per-test
# ``db`` fixture's ``truncate_all`` runs. Without it, running
# ``test_whatsapp.py`` in isolation produces an empty TRUNCATE.
from backend.main import app  # noqa: F401
from backend.services import whatsapp as wa


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the service at a fake Evolution base URL.

    Settings is frozen, so we mutate the module-bound copy in place
    via ``object.__setattr__``. the service reads attributes off
    the same singleton."""
    from pydantic import SecretStr

    from backend.config import settings

    object.__setattr__(settings, "evolution_url", "http://evo.test")
    object.__setattr__(settings, "evolution_api_key", SecretStr("test-key"))
    object.__setattr__(settings, "evolution_instance", "test-instance")
    monkeypatch.setattr(wa, "_last_seen", None)


def _unconfigure() -> None:
    from backend.config import settings

    object.__setattr__(settings, "evolution_url", None)
    object.__setattr__(settings, "evolution_api_key", None)
    object.__setattr__(settings, "evolution_instance", None)


# -------- RBAC ------------------------------------------------------


def test_status_requires_auth(client) -> None:
    r = client.get("/api/v1/whatsapp/status")
    assert r.status_code == 401


def test_status_rejects_organiser(client, organiser_token) -> None:
    r = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


def test_send_rejects_organiser(client, organiser_token) -> None:
    r = client.post(
        "/api/v1/whatsapp/send",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"number": "31612345678", "text": "hi"},
    )
    assert r.status_code == 403


def test_logout_rejects_organiser(client, organiser_token) -> None:
    r = client.post(
        "/api/v1/whatsapp/logout",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


# -------- Not-configured fallback -----------------------------------


def test_status_when_not_configured(client, admin_headers) -> None:
    _unconfigure()
    r = client.get("/api/v1/whatsapp/status", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"state": "not_configured"}


def test_qr_503_when_not_configured(client, admin_headers) -> None:
    _unconfigure()
    r = client.get("/api/v1/whatsapp/qr", headers=admin_headers)
    assert r.status_code == 503


def test_send_503_when_not_configured(client, admin_headers) -> None:
    _unconfigure()
    r = client.post(
        "/api/v1/whatsapp/send",
        headers=admin_headers,
        json={"number": "31612345678", "text": "hi"},
    )
    assert r.status_code == 503


# -------- Happy path (mocked Evolution) -----------------------------


@respx.mock
def test_status_when_configured(client, admin_headers, monkeypatch) -> None:
    _configure(monkeypatch)
    respx.get("http://evo.test/instance/connectionState/test-instance").mock(
        return_value=httpx.Response(200, json={"instance": {"state": "open"}})
    )
    r = client.get("/api/v1/whatsapp/status", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"state": "open"}


@respx.mock
def test_status_returns_unknown_when_evolution_unreachable(
    client, admin_headers, monkeypatch
) -> None:
    """If the Evolution host can't be reached (DNS failure,
    container down, wrong network), ``/status`` must return 200
    with ``state=unknown`` rather than 500. ``fetchMe`` calls
    this on every page load; a 500 here would spam Sentry on
    every nav and pollute the access log."""
    _configure(monkeypatch)
    respx.get("http://evo.test/instance/connectionState/test-instance").mock(
        side_effect=httpx.ConnectError("Temporary failure in name resolution")
    )
    r = client.get("/api/v1/whatsapp/status", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"state": "unknown"}


@respx.mock
def test_send_forwards_to_evolution(client, admin_headers, monkeypatch) -> None:
    _configure(monkeypatch)
    route = respx.post("http://evo.test/message/sendText/test-instance").mock(
        return_value=httpx.Response(200, json={"key": {"id": "abc"}})
    )
    r = client.post(
        "/api/v1/whatsapp/send",
        headers=admin_headers,
        json={"number": "31612345678", "text": "Hoi Alice"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["apikey"] == "test-key"


@respx.mock
def test_logout_calls_delete_instance(client, admin_headers, monkeypatch) -> None:
    _configure(monkeypatch)
    logout_route = respx.post("http://evo.test/instance/logout/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )
    delete_route = respx.delete("http://evo.test/instance/delete/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )
    r = client.post("/api/v1/whatsapp/logout", headers=admin_headers)
    assert r.status_code == 200
    assert logout_route.called
    assert delete_route.called


# -------- Watchdog --------------------------------------------------


@respx.mock
def test_watchdog_tears_down_when_stale(client, admin_headers, monkeypatch) -> None:
    """``_last_seen`` older than the grace window + Evolution
    reporting ``open`` ⇒ next request triggers logout + delete."""
    _configure(monkeypatch)
    # Pretend the page last heartbeated 12 minutes ago, longer
    # than ``_WATCHDOG_GRACE`` (10 minutes in prod) so the
    # tear-down branch fires.
    monkeypatch.setattr(
        wa, "_last_seen", _dt.datetime.now(_dt.UTC) - _dt.timedelta(minutes=12)
    )
    respx.get("http://evo.test/instance/connectionState/test-instance").mock(
        return_value=httpx.Response(200, json={"instance": {"state": "open"}})
    )
    logout_route = respx.post("http://evo.test/instance/logout/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )
    delete_route = respx.delete("http://evo.test/instance/delete/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )

    r = client.get("/api/v1/whatsapp/status", headers=admin_headers)
    assert r.status_code == 200
    assert logout_route.called, "watchdog should have logged out"
    assert delete_route.called, "watchdog should have deleted the instance"


@respx.mock
def test_watchdog_quiet_when_fresh(client, admin_headers, monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr(wa, "_last_seen", _dt.datetime.now(_dt.UTC))
    respx.get("http://evo.test/instance/connectionState/test-instance").mock(
        return_value=httpx.Response(200, json={"instance": {"state": "open"}})
    )
    delete_route = respx.delete("http://evo.test/instance/delete/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )
    client.get("/api/v1/whatsapp/status", headers=admin_headers)
    assert not delete_route.called, "watchdog should not fire while fresh"


@respx.mock
def test_heartbeat_bumps_last_seen(client, admin_headers, monkeypatch) -> None:
    _configure(monkeypatch)
    # Stale to start.
    monkeypatch.setattr(
        wa, "_last_seen", _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=999)
    )
    respx.get("http://evo.test/instance/connectionState/test-instance").mock(
        return_value=httpx.Response(200, json={"instance": {"state": "close"}})
    )
    # Connection is "close" so watchdog won't tear down. the
    # interesting assertion is that the heartbeat has refreshed
    # ``_last_seen`` by the time the call returns.
    r = client.post("/api/v1/whatsapp/heartbeat", headers=admin_headers)
    assert r.status_code == 200
    assert wa._last_seen is not None
    assert (_dt.datetime.now(_dt.UTC) - wa._last_seen).total_seconds() < 5


# -------- /qr happy path + RBAC -------------------------------------


@respx.mock
def test_qr_happy_path(client, admin_headers, monkeypatch) -> None:
    """``/qr`` returns whatever Evolution gives us (preferring
    ``base64`` then ``qrcode`` then ``code``) plus the pairing
    code. ``ensure_instance()`` is hit first; we mock it as
    already-existing (409)."""
    _configure(monkeypatch)
    respx.post("http://evo.test/instance/create").mock(
        return_value=httpx.Response(409, json={"error": "exists"})
    )
    respx.get("http://evo.test/instance/connect/test-instance").mock(
        return_value=httpx.Response(
            200,
            json={"base64": "data:image/png;base64,AAA", "pairingCode": "ABCD-1234"},
        )
    )
    r = client.get("/api/v1/whatsapp/qr", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["qr"] == "data:image/png;base64,AAA"
    assert body["pairingCode"] == "ABCD-1234"


def test_qr_requires_auth(client) -> None:
    r = client.get("/api/v1/whatsapp/qr")
    assert r.status_code == 401


def test_qr_rejects_organiser(client, organiser_token) -> None:
    r = client.get(
        "/api/v1/whatsapp/qr",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


# -------- /heartbeat + /logout RBAC ---------------------------------


def test_heartbeat_requires_auth(client) -> None:
    r = client.post("/api/v1/whatsapp/heartbeat")
    assert r.status_code == 401


def test_heartbeat_rejects_organiser(client, organiser_token) -> None:
    r = client.post(
        "/api/v1/whatsapp/heartbeat",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


def test_logout_requires_auth(client) -> None:
    r = client.post("/api/v1/whatsapp/logout")
    assert r.status_code == 401


# -------- Service-level branches not exercised by the routes --------


@respx.mock
def test_send_text_raises_on_evolution_error(monkeypatch) -> None:
    """``send_text`` propagates a 4xx/5xx from Evolution as an
    HTTPStatusError so the route returns a 500. Without this, a
    failed send would silently report ``ok``."""
    import asyncio

    _configure(monkeypatch)
    respx.post("http://evo.test/message/sendText/test-instance").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(wa.send_text("31612345678", "hi"))


@respx.mock
def test_ensure_instance_swallows_409_already_exists(monkeypatch) -> None:
    """The instance-create call must be idempotent: 403/409 means
    the instance is already there, not an error to surface."""
    import asyncio

    _configure(monkeypatch)
    route = respx.post("http://evo.test/instance/create").mock(
        return_value=httpx.Response(409, json={"error": "already exists"})
    )
    asyncio.run(wa.ensure_instance())
    assert route.called  # didn't raise


@respx.mock
def test_ensure_instance_treats_201_as_created(monkeypatch) -> None:
    import asyncio

    _configure(monkeypatch)
    respx.post("http://evo.test/instance/create").mock(
        return_value=httpx.Response(201, json={"instance": {"instanceName": "test-instance"}})
    )
    asyncio.run(wa.ensure_instance())  # no exception


# -------- Auth-logout integration -----------------------------------


@respx.mock
def test_auth_logout_wipes_whatsapp_session(client, admin_headers, monkeypatch) -> None:
    """``POST /auth/logout`` tears down any linked Evolution session
    so the next visit starts clean."""
    _configure(monkeypatch)
    logout_route = respx.post("http://evo.test/instance/logout/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )
    delete_route = respx.delete("http://evo.test/instance/delete/test-instance").mock(
        return_value=httpx.Response(200, json={})
    )
    r = client.post("/api/v1/auth/logout", headers=admin_headers)
    assert r.status_code == 204
    assert logout_route.called
    assert delete_route.called


def test_auth_logout_when_whatsapp_unconfigured(client, admin_headers) -> None:
    """No env vars → nothing to tear down, but logout still
    succeeds. Must never 5xx on a sign-out."""
    _unconfigure()
    r = client.post("/api/v1/auth/logout", headers=admin_headers)
    assert r.status_code == 204


def test_auth_logout_requires_auth(client) -> None:
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 401


# -------- Privacy: no PII in logs -----------------------------------


def test_no_pii_in_whatsapp_logs() -> None:
    """``services/whatsapp.py`` must never log phone numbers or
    message bodies. The CLAUDE.md privacy rule is asserted at the
    source level: ``number=`` and ``text=`` and ``body=`` cannot
    appear inside a ``logger.*`` call in this module."""
    import pathlib
    import re

    src = pathlib.Path(wa.__file__).read_text(encoding="utf-8")
    pattern = re.compile(
        r"logger\.(?:info|warning|error|debug|exception)\([^)]*"
        r"\b(?:number|text|body|message)=",
        re.DOTALL,
    )
    assert not pattern.search(src), "WhatsApp logger leak: number/text/body kwarg in logger call"
