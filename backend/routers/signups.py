import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import EmailChannel, EmailDispatch, EmailStatus, Event, Signup, User
from ..schemas.events import SignupAck, SignupCreate, SignupEditIn, SignupEditOut
from ..services import access, edit_token, encryption
from ..services import events as events_svc
from ..services.events import now_wallclock
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
    event_in_future = event.starts_at > now_wallclock()

    has_email = bool(data.email)
    channels: list[EmailChannel] = []
    if has_email and event.feedback_enabled:
        channels.append(EmailChannel.FEEDBACK)
    if has_email and event.reminder_enabled and event_in_future:
        channels.append(EmailChannel.REMINDER)

    raw_token, token_hash = edit_token.new_edit_token()
    signup = Signup(
        event_id=event.id,
        display_name=data.display_name,
        party_size=data.party_size,
        source_choice=data.source_choice,
        help_choices=data.help_choices,
        edit_token_hash=token_hash,
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
    return SignupAck(edit_token=raw_token)


def _signup_by_token(db: Session, token: str) -> Signup:
    """Resolve an edit-link token to its signup. 404 if no match; 410
    if the event is archived or already over (editing headcount for a
    past event is moot). The signup carries no email and no key to its
    dispatch rows, so this read-back can't reach the address."""
    signup = db.query(Signup).filter(Signup.edit_token_hash == edit_token.hash_edit_token(token)).first()
    if signup is None:
        raise HTTPException(status_code=404, detail="This edit link is not valid.")
    event = db.query(Event).filter(Event.id == signup.event_id).first()
    if event is None or event.archived_at is not None or event.ends_at <= now_wallclock():
        raise HTTPException(status_code=410, detail="This event is no longer open for changes.")
    return signup


@router.get("/by-token/{token}", response_model=SignupEditOut)
def get_signup(token: str, db: Session = Depends(get_db)) -> SignupEditOut:
    """Current values of a signup, for pre-filling the edit form.
    Email is never returned (it isn't reachable from a signup)."""
    signup = _signup_by_token(db, token)
    return SignupEditOut(
        display_name=signup.display_name,
        party_size=signup.party_size,
        source_choice=signup.source_choice,
        help_choices=signup.help_choices,
    )


@router.put("/by-token/{token}", response_model=SignupEditOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def update_signup(
    request: Request,
    token: str,
    data: SignupEditIn,
    db: Session = Depends(get_db),
) -> SignupEditOut:
    """Update a signup's non-email fields via its edit-link token.
    Email + dispatch rows are untouched — there is no path from a
    signup to its encrypted address (principle #2)."""
    signup = _signup_by_token(db, token)
    event = db.query(Event).filter(Event.id == signup.event_id).first()
    assert event is not None  # _signup_by_token already proved it
    if data.source_choice is not None and data.source_choice not in event.source_options:
        raise HTTPException(status_code=400, detail="source_choice must match one of the event's options")
    invalid_help = [c for c in data.help_choices if c not in event.help_options]
    if invalid_help:
        raise HTTPException(
            status_code=400,
            detail=f"help_choices must be a subset of the event's help_options: {invalid_help}",
        )
    signup.display_name = data.display_name
    signup.party_size = data.party_size
    signup.source_choice = data.source_choice
    signup.help_choices = data.help_choices
    db.commit()
    logger.info("signup_edited", event_id=signup.event_id, signup_id=signup.id)
    return SignupEditOut(
        display_name=signup.display_name,
        party_size=signup.party_size,
        source_choice=signup.source_choice,
        help_choices=signup.help_choices,
    )


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
