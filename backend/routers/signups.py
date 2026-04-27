from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Signup
from ..schemas.events import SignupAck, SignupCreate
from ..services import encryption
from ..services import events as events_svc
from ..services.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["signups"])


@router.post("/by-slug/{slug}/signups", response_model=SignupAck, status_code=201)
@limiter.limit("30/hour")
def create_signup(
    request: Request,
    slug: str,
    data: SignupCreate,
    db: Session = Depends(get_db),
) -> SignupAck:
    event = events_svc.get_public_event_by_slug(db, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if data.source_choice is not None and data.source_choice not in event.source_options:
        raise HTTPException(status_code=400, detail="source_choice must match one of the event's options")
    invalid_help = [c for c in data.help_choices if c not in event.help_options]
    if invalid_help:
        raise HTTPException(
            status_code=400,
            detail=f"help_choices must be a subset of the event's help_options: {invalid_help}",
        )

    # Decide which channels apply for this signup. Reminders apply
    # whenever the event hasn't started yet — the worker's own
    # window check (``REMINDER_WINDOW``) handles "fire now vs.
    # wait" once we're inside the 3-day pre-event period.
    now = datetime.now(UTC)
    starts_at = event.starts_at
    if starts_at.tzinfo is None:
        # SQLite returns naive datetimes; we wrote them as UTC.
        starts_at = starts_at.replace(tzinfo=UTC)
    event_in_future = starts_at > now

    will_send_feedback = bool(data.email) and event.questionnaire_enabled
    will_send_reminder = (
        bool(data.email) and event.reminder_enabled and event_in_future
    )
    will_send_anything = will_send_feedback or will_send_reminder
    encrypted = (
        encryption.encrypt(data.email)
        if will_send_anything and data.email
        else None
    )
    signup = Signup(
        # Point at the stable logical id so signups survive every edit.
        event_id=event.entity_id,
        display_name=data.display_name,
        party_size=data.party_size,
        source_choice=data.source_choice,
        help_choices=data.help_choices,
        encrypted_email=encrypted,
        feedback_email_status="pending" if will_send_feedback else "not_applicable",
        reminder_email_status="pending" if will_send_reminder else "not_applicable",
    )
    db.add(signup)
    db.commit()
    logger.info("signup_created", event_id=event.entity_id, party_size=data.party_size)
    return SignupAck()
