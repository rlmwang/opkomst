"""Stateless proxy to a self-hosted Evolution API instance.

The WhatsApp blast tool (``docs/plan-whatsapp-blast.md``) is a
one-off admin utility: paste a list of names + phone numbers, type
a message, send. It does **not** integrate with the data model ,
no DB writes, no PII at rest. This module is the only place that
talks to Evolution; the router is a thin authn/authz wrapper.

Two pieces of in-memory state, deliberately:

* ``_last_seen``. bumped by the page's heartbeat. The watchdog
  uses it to log out (and wipe) the linked WhatsApp session if the
  page goes silent for a minute. That's how "forget when the user
  leaves" is enforced even when the browser dies and never sends a
  ``pagehide`` beacon.
* The shared ``httpx.AsyncClient``. opened lazily, closed on app
  shutdown. Reused so connection setup isn't paid per request.

Restart of the backend = clean slate. That's fine: Evolution holds
the linked-device session itself, and any blast in flight is
cancelled with the page anyway.

No PII in logs from this module. Phone numbers and message bodies
must never appear in log lines. only route + outcome counters.
``tests/test_privacy.py`` greps for offenders.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Literal

import httpx
import structlog

from backend.config import settings

logger = structlog.get_logger()

# Watchdog grace: the page heartbeats every 15s. If we haven't
# heard from it for this long while the WhatsApp session is
# linked, tear the session down. 60s gives one missed heartbeat
# of slack before action.
_WATCHDOG_GRACE = _dt.timedelta(seconds=60)

# Module-level. Single-process, in-memory. A fresh worker means a
# missed beat is a tear-down, which is the conservative direction.
_last_seen: _dt.datetime | None = None
_client: httpx.AsyncClient | None = None


ConnectionState = Literal["open", "connecting", "close", "unknown"]


class WhatsAppNotConfigured(RuntimeError):
    """Raised when the three EVOLUTION_* env vars aren't all set.

    Routes catch this and return 503; the frontend surfaces a
    "tool disabled in this deployment" message instead of crashing.
    """


def is_configured() -> bool:
    return bool(settings.evolution_url and settings.evolution_api_key and settings.evolution_instance)


def _require_config() -> tuple[str, str, str]:
    if not is_configured():
        raise WhatsAppNotConfigured("EVOLUTION_URL / EVOLUTION_API_KEY / EVOLUTION_INSTANCE not set")
    assert settings.evolution_url is not None
    assert settings.evolution_api_key is not None
    assert settings.evolution_instance is not None
    return (
        settings.evolution_url.rstrip("/"),
        settings.evolution_api_key.get_secret_value(),
        settings.evolution_instance,
    )


def _get_client() -> httpx.AsyncClient:
    """Lazy singleton. Closed by ``shutdown()`` on app shutdown."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    return _client


async def shutdown() -> None:
    """Called from FastAPI's shutdown hook so the pool drains."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _request(method: str, path: str, *, json: Any | None = None) -> httpx.Response:
    base, key, _ = _require_config()
    headers = {"apikey": key, "Content-Type": "application/json"}
    return await _get_client().request(method, f"{base}{path}", headers=headers, json=json)


# ---- Instance lifecycle --------------------------------------------


async def ensure_instance() -> None:
    """Create the configured instance if it doesn't exist.

    Idempotent: Evolution returns 403/409 on duplicate names, both
    of which we swallow silently. Any other status is logged.
    """
    _, _, instance = _require_config()
    res = await _request(
        "POST",
        "/instance/create",
        json={"instanceName": instance, "integration": "WHATSAPP-BAILEYS", "qrcode": True},
    )
    if res.status_code in (200, 201):
        logger.info("whatsapp.instance_create", outcome="created")
        return
    if res.status_code in (403, 409):
        # Already exists. fine.
        return
    logger.warning("whatsapp.instance_create", outcome="unexpected", status=res.status_code)


async def status() -> ConnectionState:
    """Connection state of the linked WhatsApp session.

    Degrades gracefully when Evolution is unreachable: a network
    error returns ``"unknown"`` rather than propagating, so the
    page-load path (``/auth/me`` indirectly calls this via
    ``auth.fetchMe``) never 500s on a misconfigured deploy. The
    frontend already treats anything other than ``"open"`` as
    "no session" and hides the tab, so this is the right
    default.
    """
    _, _, instance = _require_config()
    try:
        res = await _request("GET", f"/instance/connectionState/{instance}")
    except httpx.RequestError:
        logger.warning("whatsapp.status", outcome="unreachable")
        return "unknown"
    if res.status_code == 404:
        return "close"
    if res.status_code != 200:
        logger.warning("whatsapp.status", outcome="error", status=res.status_code)
        return "unknown"
    body = res.json()
    state = (body.get("instance") or {}).get("state") or body.get("state")
    if state in ("open", "connecting", "close"):
        return state  # type: ignore[return-value]
    return "unknown"


async def qr() -> dict[str, Any]:
    """Fetch a fresh pairing QR. Creates the instance first if needed."""
    await ensure_instance()
    _, _, instance = _require_config()
    res = await _request("GET", f"/instance/connect/{instance}")
    if res.status_code != 200:
        logger.warning("whatsapp.qr", outcome="error", status=res.status_code)
        res.raise_for_status()
    body = res.json()
    return {
        "qr": body.get("base64") or body.get("qrcode") or body.get("code"),
        "pairingCode": body.get("pairingCode"),
    }


async def logout() -> None:
    _, _, instance = _require_config()
    res = await _request("POST", f"/instance/logout/{instance}")
    logger.info("whatsapp.logout", outcome="ok" if res.status_code < 400 else "error", status=res.status_code)


async def delete_instance() -> None:
    """Full wipe: logout + remove session keys from Evolution's volume.

    Used by the page's "Disconnect" button and by the app-logout
    flow so the next visit starts from a clean QR scan.
    """
    _, _, instance = _require_config()
    # Evolution requires logout before delete on a connected session.
    try:
        await logout()
    except Exception:
        pass
    res = await _request("DELETE", f"/instance/delete/{instance}")
    logger.info("whatsapp.delete", outcome="ok" if res.status_code < 400 else "error", status=res.status_code)


# ---- Sending --------------------------------------------------------


async def send_text(number: str, text: str) -> dict[str, Any]:
    """Send one text message. Returns the Evolution response body.

    Rate-limited at the route level. Caller paces the loop.
    Logs route + outcome only. never the number or text.
    """
    _, _, instance = _require_config()
    res = await _request(
        "POST",
        f"/message/sendText/{instance}",
        json={"number": number, "text": text},
    )
    if res.status_code >= 400:
        logger.warning("whatsapp.send", outcome="error", status=res.status_code)
        res.raise_for_status()
    logger.info("whatsapp.send", outcome="ok")
    return res.json()


# ---- Watchdog -------------------------------------------------------


def heartbeat_tick() -> None:
    """Bump the page's last-seen timestamp."""
    global _last_seen
    _last_seen = _dt.datetime.now(_dt.UTC)


async def watchdog_check() -> None:
    """If the page has gone silent past the grace period and a session
    is still linked, tear it down. Called lazily from the router on
    every WhatsApp request. no background task, no scheduler."""
    global _last_seen
    if _last_seen is None:
        return
    if _dt.datetime.now(_dt.UTC) - _last_seen <= _WATCHDOG_GRACE:
        return
    # Past grace. Tear down if connected.
    try:
        if await status() == "open":
            logger.info("whatsapp.watchdog", outcome="tearing_down")
            await delete_instance()
    finally:
        _last_seen = None
