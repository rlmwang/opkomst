"""Admin-only proxy to the Evolution API.

Stateless. No DB writes, no model mutations, no PII at rest. The
business logic lives in ``services/whatsapp.py``; this module is
the FastAPI scaffolding (auth, rate limits, error mapping).

The watchdog runs lazily. every WhatsApp request first calls
``watchdog_check()`` so the linked session gets torn down within
a minute of the page going silent. No background scheduler, no
cron entry: the page polls, the watchdog rides along.

Logging is deliberately sparse. Phone numbers and message bodies
must never appear in log lines; the service module enforces this
on the way out, and the privacy audit greps for offenders.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_admin
from ..models import User
from ..schemas.whatsapp import (
    HeartbeatResponse,
    QrResponse,
    SendRequest,
    SendResponse,
    StatusResponse,
)
from ..services import whatsapp as wa
from ..services.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])


async def _watchdog() -> None:
    """Lazy watchdog. runs before every WhatsApp call. Cheap when
    the timestamp is fresh, tears the session down when stale."""
    try:
        await wa.watchdog_check()
    except Exception:
        # The watchdog failing must never break the actual request;
        # the next tick will retry. Logged at debug level only.
        logger.debug("whatsapp.watchdog", outcome="error")


@router.get("/status", response_model=StatusResponse)
async def get_status(_: User = Depends(require_admin)) -> StatusResponse:
    await _watchdog()
    if not wa.is_configured():
        return StatusResponse(state="not_configured")
    state = await wa.status()
    return StatusResponse(state=state)


@router.get("/qr", response_model=QrResponse)
async def get_qr(_: User = Depends(require_admin)) -> QrResponse:
    await _watchdog()
    if not wa.is_configured():
        raise HTTPException(status_code=503, detail="WhatsApp tool not configured")
    payload = await wa.qr()
    return QrResponse(qr=payload.get("qr"), pairingCode=payload.get("pairingCode"))


@router.post("/heartbeat", response_model=HeartbeatResponse)
@limiter.limit("120/minute")
async def heartbeat(request: Request, _: User = Depends(require_admin)) -> HeartbeatResponse:
    """Page liveness ping. Bumps ``_last_seen`` and returns current
    state in one round-trip so the page can poll a single endpoint.

    The 120/min cap is well above the page's 15s interval; it's a
    safety net against a runaway tab, not a usage cap."""
    await _watchdog()
    wa.heartbeat_tick()
    if not wa.is_configured():
        return HeartbeatResponse(state="not_configured")
    state = await wa.status()
    return HeartbeatResponse(state=state)


@router.post("/send", response_model=SendResponse)
@limiter.limit("30/minute")
async def send(request: Request, body: SendRequest, _: User = Depends(require_admin)) -> SendResponse:
    """Send one text message. Client paces the loop; this cap is a
    backstop against a runaway send."""
    await _watchdog()
    if not wa.is_configured():
        raise HTTPException(status_code=503, detail="WhatsApp tool not configured")
    await wa.send_text(body.number, body.text)
    return SendResponse(ok=True)


@router.post("/logout", response_model=SendResponse)
@limiter.limit("10/minute")
async def logout(request: Request, _: User = Depends(require_admin)) -> SendResponse:
    """Full wipe: logs out and deletes the Evolution instance, so
    the next visit starts from a fresh QR."""
    await _watchdog()
    if not wa.is_configured():
        return SendResponse(ok=True)
    await wa.delete_instance()
    return SendResponse(ok=True)
