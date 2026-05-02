"""Chapter-scoped event CRUD + organiser-side reads.

Five mutating endpoints (create / update / archive / restore /
send-emails-now) and four read endpoints (list / list-archived /
stats / signups). All require an approved user; all are scoped
to the user's chapter via ``access.get_event_for_user`` (single)
or ``_scope_filter`` (lists).

Public-by-slug surfaces (ICS, QR, previews, the JSON the public
form reads) live in ``routers/events_public.py``.

Read aggregates (chapter-name + attendee-total enrichment, source/
help breakdowns, signups summary) live in ``services/event_stats.py``
where they can be unit-tested without a router fixture.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from ..auth import require_approved
from ..database import get_db
from ..models import EmailChannel, Event, User
from ..schemas.events import EventCreate, EventOut, EventStatsOut, SignupSummaryOut
from ..services import access, event_stats, mail_lifecycle
from ..services.rate_limit import Limits, limiter
from ..services.slug import new_slug

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("", response_model=EventOut, status_code=201)
@limiter.limit(Limits.ORG_RARE)
def create_event(
    request: Request,
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    # Caller-supplied chapter must be one the user actually
    # belongs to. The frontend's chapter dropdown is already
    # scoped to the user's live chapters; this is the
    # defence-in-depth check.
    access.assert_user_can_assign_chapter(db, user, data.chapter_id)
    event = Event(
        slug=new_slug(),
        name=data.name,
        topic=data.topic,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        source_options=data.source_options,
        help_options=data.help_options,
        feedback_enabled=data.feedback_enabled,
        reminder_enabled=data.reminder_enabled,
        locale=data.locale,
        chapter_id=data.chapter_id,
        created_by=user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info(
        "event_created",
        event_id=event.id,
        actor_id=user.id,
        chapter_id=data.chapter_id,
    )
    return event_stats.to_out(db, event)


def _list_filter(db: Session, user: User, chapter_id: str | None) -> ColumnElement[bool]:
    """Build the WHERE clause for an event list. ``chapter_id`` is
    the optional UI filter; without it we return every event in
    the user's full chapter set. The clause goes through
    ``access.event_scope_filter`` so the access rule (admins
    see everything, organisers scoped to memberships) is
    centralised."""
    base = access.event_scope_filter(db, user)
    if chapter_id is None:
        return base
    access.assert_user_can_assign_chapter(db, user, chapter_id)
    return Event.chapter_id == chapter_id


@router.get("", response_model=list[EventOut])
def list_events(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    rows = (
        db.query(Event)
        .filter(_list_filter(db, user, chapter_id), Event.archived_at.is_(None))
        .order_by(Event.starts_at.desc())
        .all()
    )
    return event_stats.enrich(db, rows)


@router.get("/archived", response_model=list[EventOut])
def list_archived_events(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    rows = (
        db.query(Event)
        .filter(_list_filter(db, user, chapter_id), Event.archived_at.is_not(None))
        .order_by(Event.created_at.desc())
        .all()
    )
    return event_stats.enrich(db, rows)


@router.post("/{event_id}/archive", response_model=EventOut)
@limiter.limit(Limits.ORG_RARE)
def archive_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = access.get_event_for_user(db, event_id, user)
    if event.archived_at is not None:
        raise HTTPException(status_code=409, detail="Already archived")
    event.archived_at = datetime.now(UTC)
    db.commit()
    db.refresh(event)
    logger.info("event_archived", event_id=event.id, actor_id=user.id)
    return event_stats.to_out(db, event)


@router.post("/{event_id}/restore", response_model=EventOut)
@limiter.limit(Limits.ORG_RARE)
def restore_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = access.get_event_for_user(db, event_id, user)
    if event.archived_at is None:
        raise HTTPException(status_code=409, detail="Not archived")
    event.archived_at = None
    db.commit()
    db.refresh(event)
    logger.info("event_restored", event_id=event.id, actor_id=user.id)
    return event_stats.to_out(db, event)


@router.delete("/{event_id}", status_code=204)
@limiter.limit(Limits.ORG_RARE)
def delete_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Hard-delete an archived event. Refuses if the event isn't
    archived first — accidentally hard-deleting a live event
    with sign-ups would be a data-loss footgun. Cascades through
    ``signups`` / ``email_dispatches`` / ``feedback_responses`` /
    ``feedback_tokens`` via the FK ``ON DELETE CASCADE``s in the
    schema; the row + its dependents go with one DELETE."""
    event = access.get_event_for_user(db, event_id, user)
    if event.archived_at is None:
        raise HTTPException(status_code=409, detail="Archive the event before deleting it")
    db.delete(event)
    db.commit()
    logger.info("event_deleted", event_id=event_id, actor_id=user.id)


@router.post("/{event_id}/send-emails/{channel}", status_code=200)
@limiter.limit(Limits.SEND_EMAILS_NOW)
def send_emails_now(
    request: Request,
    event_id: str,
    channel: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> dict[str, int]:
    """Manually trigger the worker for one channel on a single
    event. Re-use of the generic dispatcher means the reminder
    + feedback "send now" buttons share one endpoint and one
    rate-limit budget."""
    event = access.get_event_for_user(db, event_id, user)
    try:
        ch = EmailChannel(channel)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown channel") from None
    if not mail_lifecycle.channel_enabled_for(ch, event):
        raise HTTPException(status_code=409, detail=f"Channel {ch.value} is disabled for this event")
    processed = mail_lifecycle.run_for_event(ch, event_id)
    logger.info(
        "emails_triggered",
        event_id=event_id,
        channel=channel,
        actor_id=user.id,
        processed=processed,
    )
    return {"processed": processed}


@router.put("/{event_id}", response_model=EventOut)
@limiter.limit(Limits.ORG_WRITE)
def update_event(
    request: Request,
    event_id: str,
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    event = access.get_event_for_user(db, event_id, user)
    was_feedback = event.feedback_enabled
    was_reminder = event.reminder_enabled

    # Chapter changes are allowed (the user might've picked the
    # wrong chapter at create time) but the new one still has to
    # be in the user's set, same as create.
    if data.chapter_id != event.chapter_id:
        access.assert_user_can_assign_chapter(db, user, data.chapter_id)

    event.name = data.name
    event.chapter_id = data.chapter_id
    event.topic = data.topic
    event.location = data.location
    event.latitude = data.latitude
    event.longitude = data.longitude
    event.starts_at = data.starts_at
    event.ends_at = data.ends_at
    event.source_options = data.source_options
    event.help_options = data.help_options
    event.feedback_enabled = data.feedback_enabled
    event.reminder_enabled = data.reminder_enabled
    event.locale = data.locale

    # Toggle-off cleanup: when an organiser disables a channel,
    # delete pending dispatches for it and wipe ciphertext for
    # signups that no longer have any pending dispatch.
    retired: set[EmailChannel] = set()
    if was_feedback and not data.feedback_enabled:
        retired.add(EmailChannel.FEEDBACK)
    if was_reminder and not data.reminder_enabled:
        retired.add(EmailChannel.REMINDER)
    mail_lifecycle.retire_event_channels(db, event_id=event.id, channels=retired)
    db.commit()
    db.refresh(event)
    logger.info("event_updated", event_id=event.id, actor_id=user.id)
    return event_stats.to_out(db, event)


@router.get("/{event_id}/stats", response_model=EventStatsOut)
def event_stats_endpoint(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventStatsOut:
    event = access.get_event_for_user(db, event_id, user)
    return event_stats.per_event_stats(db, event)


@router.get("/{event_id}/signups", response_model=list[SignupSummaryOut])
def event_signups(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[SignupSummaryOut]:
    """Per-signup list for the organiser details page. Returns
    display_name + party_size + help_choices — never email,
    source, or feedback-email status."""
    event = access.get_event_for_user(db, event_id, user)
    return event_stats.signups_summary(db, event)
