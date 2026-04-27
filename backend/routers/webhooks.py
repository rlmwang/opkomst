"""Inbound provider webhooks.

Currently handles Scaleway TEM event notifications (delivery / bounce
/ complaint). The Scaleway TEM webhook posts JSON containing the
``message_id`` we set as the ``Message-ID`` header on outbound
emails; we look up the signup by that id and update its
``feedback_email_status``.

The request must carry an ``X-Scaleway-Signature`` HMAC-SHA256 of
the raw body using ``SCALEWAY_WEBHOOK_SECRET``. The secret is
required: if it isn't set the route refuses every request, on the
theory that a forgotten env var in prod is the failure mode this
endpoint is least allowed to silently absorb. Local dev that wants
to fire unsigned posts can set
``OPKOMST_ALLOW_UNSIGNED_WEBHOOKS=1`` to bypass the check.

See https://www.scaleway.com/en/docs/managed-services/transactional-email/api-cli/sending-email-events/
"""

import hashlib
import hmac
import os

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Signup

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Scaleway TEM event types that should mark a signup's email as
# undeliverable. Soft bounces, delivery confirmations, and clicks /
# opens are ignored — we only care about hard failure for the UI.
_BOUNCE_EVENTS = {"email_dropped", "email_mailbox_not_found", "email_bounce", "email_blocklisted"}
_COMPLAINT_EVENTS = {"email_spam", "email_complained"}


def _verify_signature(raw_body: bytes, header_value: str | None) -> None:
    if os.environ.get("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS") == "1":
        # Explicit opt-in for local development. Never set in prod.
        return
    secret = os.environ.get("SCALEWAY_WEBHOOK_SECRET", "")
    if not secret:
        # Fail closed: no secret means we can't verify, so we don't
        # accept. A forgotten env var must not silently turn this
        # endpoint into a public mark-everything-bounced button.
        raise HTTPException(status_code=503, detail="Webhook signing not configured")
    if not header_value:
        raise HTTPException(status_code=401, detail="Missing signature header")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, header_value):
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post("/scaleway-email", status_code=204)
async def scaleway_email_event(
    request: Request,
    x_scaleway_signature: str | None = Header(default=None, alias="X-Scaleway-Signature"),
    db: Session = Depends(get_db),
) -> None:
    raw = await request.body()
    _verify_signature(raw, x_scaleway_signature)

    payload = await request.json()
    # Scaleway TEM may post a single event or a batch. Normalise.
    events = payload if isinstance(payload, list) else [payload]

    for ev in events:
        event_type = (ev.get("type") or ev.get("event") or "").lower()
        message_id = ev.get("message_id") or ev.get("messageId")
        if not message_id:
            continue

        signup = db.query(Signup).filter(Signup.feedback_message_id == message_id).first()
        if not signup:
            # Could be from a previous deployment, or a message we never
            # tracked. Log and move on — webhooks are fire-and-forget.
            logger.info("scaleway_event_unmatched", event_type=event_type, message_id=message_id)
            continue

        if event_type in _BOUNCE_EVENTS:
            signup.feedback_email_status = "bounced"
            db.add(signup)
            logger.info("feedback_email_bounced", signup_id=signup.id, event_type=event_type)
        elif event_type in _COMPLAINT_EVENTS:
            signup.feedback_email_status = "complaint"
            db.add(signup)
            logger.info("feedback_email_complaint", signup_id=signup.id, event_type=event_type)
        # email_delivered / email_open / email_click / soft bounces:
        # leave "sent" alone. Soft bounces in particular often resolve
        # on their own and would mislead organisers if we surfaced them.

    db.commit()
