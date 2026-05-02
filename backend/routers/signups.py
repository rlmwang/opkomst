from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import EmailChannel, EmailDispatch, EmailStatus, Signup, User
from ..schemas.events import SignupAck, SignupCreate
from ..services import access, encryption
from ..services import events as events_svc
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["signups"])


@router.post("/by-slug/{slug}/signups", response_model=SignupAck, status_code=201)
@limiter.limit(Limits.PUBLIC_SIGNUP)
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
    # only when the event hasn't started yet — the worker's window
    # check would skip a row whose event is already in the past;
    # creating a row for that case would just be debt for the
    # reaper to clean up later. Feedback applies whenever its
    # toggle is on.
    event_in_future = event.starts_at > datetime.now(UTC)

    has_email = bool(data.email)
    channels: list[EmailChannel] = []
    if has_email and event.feedback_enabled:
        channels.append(EmailChannel.FEEDBACK)
    if has_email and event.reminder_enabled and event_in_future:
        channels.append(EmailChannel.REMINDER)

    signup = Signup(
        event_id=event.id,
        display_name=data.display_name,
        party_size=data.party_size,
        source_choice=data.source_choice,
        help_choices=data.help_choices,
    )
    db.add(signup)

    # Each dispatch row carries its own encrypted copy of the
    # address and points directly at the event. The signup row
    # and the dispatch rows live in parallel — neither references
    # the other. Independent ciphertexts (different nonces) per
    # row; finalising nulls the address inline, deleting a row
    # deletes the address with it.
    for ch in channels:
        assert data.email is not None  # has_email gate above
        db.add(
            EmailDispatch(
                event_id=event.id,
                channel=ch,
                status=EmailStatus.PENDING,
                encrypted_email=encryption.encrypt(data.email),
            )
        )
    db.commit()
    logger.info(
        "signup_created",
        event_id=event.id,
        party_size=data.party_size,
        channels=[c.value for c in channels],
    )
    return SignupAck()


@router.delete("/{event_id}/signups/{signup_id}", status_code=204)
@limiter.limit(Limits.ORG_WRITE)
def delete_signup(
    request: Request,
    event_id: str,
    signup_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Organiser-only hard-delete of a single signup row. Targets
    the case where someone (often the organiser themselves) wants
    a stray sign-up gone — accidental submission, duplicate row,
    test data left in a real event.

    Privacy invariant unaffected: ``Signup`` carries no email, so
    deleting the row removes only headcount + display-name. Any
    pending ``EmailDispatch`` rows for this event live on by
    design (no signup_id link); the worker may still send a
    reminder/feedback email to the address the deleted signup
    submitted. That decoupling is the whole point — see
    ``models/email_dispatch.py``."""
    event = access.get_event_for_user(db, event_id, user)
    signup = db.query(Signup).filter(Signup.id == signup_id, Signup.event_id == event.id).first()
    if signup is None:
        raise HTTPException(status_code=404, detail="Signup not found")
    db.delete(signup)
    db.commit()
    logger.info("signup_deleted", event_id=event.id, signup_id=signup_id, actor_id=user.id)
