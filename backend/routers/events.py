import io
import os

import qrcode
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import Event, Signup, User
from ..schemas.events import EventCreate, EventOut, EventStatsOut
from ..services import afdelingen as afdelingen_svc
from ..services.slug import new_slug

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["events"])

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


def _attendees_for(db: Session, event_id: str) -> int:
    total = db.query(func.coalesce(func.sum(Signup.party_size), 0)).filter(Signup.event_id == event_id).scalar()
    return int(total or 0)


def _to_out(db: Session, event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        slug=event.slug,
        name=event.name,
        topic=event.topic,
        location=event.location,
        latitude=event.latitude,
        longitude=event.longitude,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        source_options=event.source_options,
        questionnaire_enabled=event.questionnaire_enabled,
        afdeling_id=event.afdeling_id,
        afdeling_name=afdelingen_svc.name_for_entity(db, event.afdeling_id),
        signup_count=_attendees_for(db, event.id),
    )


def _scope_filter(user: User):
    """Restrict an Event query to events visible to ``user``. Same
    rule for organisers and admins (small-org trust model): you only
    see your own afdeling's events. Admins move themselves into other
    afdelingen via the assign-afdeling endpoint when they need to."""
    if user.afdeling_id is None:
        # Approved users without an afdeling shouldn't exist (the
        # approve endpoint refuses), but defend against the case
        # anyway — they see nothing rather than everything.
        return Event.afdeling_id == "__no_match__"
    return Event.afdeling_id == user.afdeling_id


def _get_event_scoped(db: Session, event_id: str, user: User) -> Event:
    """Fetch an event by id, refusing if it's outside the user's
    afdeling. 404 (not 403) so we don't leak the existence of events
    in other afdelingen."""
    event = db.query(Event).filter(Event.id == event_id, _scope_filter(user)).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("", response_model=EventOut, status_code=201)
def create_event(
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    if user.afdeling_id is None:
        # require_approved already prevents this in practice (approve
        # endpoint refuses without an afdeling), but explicit beats
        # implicit for an FK assignment.
        raise HTTPException(status_code=409, detail="No afdeling assigned")
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
        questionnaire_enabled=data.questionnaire_enabled,
        afdeling_id=user.afdeling_id,
        created_by=user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info("event_created", event_id=event.id, actor_id=user.id)
    return _to_out(db, event)


@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    """Every approved organiser in the afdeling sees every active
    event in that afdeling. Cross-afdeling visibility is by design
    not a thing (admins switch their own afdeling to see another
    chapter's events)."""
    rows = (
        db.query(Event)
        .filter(_scope_filter(user), Event.archived_at.is_(None))
        .order_by(Event.starts_at.desc())
        .all()
    )
    return [_to_out(db, e) for e in rows]


@router.get("/archived", response_model=list[EventOut])
def list_archived_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    """Archived events for the user's afdeling. Restore flips them
    back to active."""
    rows = (
        db.query(Event)
        .filter(_scope_filter(user), Event.archived_at.is_not(None))
        .order_by(Event.created_at.desc())
        .all()
    )
    return [_to_out(db, e) for e in rows]


@router.post("/{event_id}/archive", response_model=EventOut)
def archive_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    from datetime import UTC, datetime

    event = _get_event_scoped(db, event_id, user)
    if event.archived_at is not None:
        raise HTTPException(status_code=409, detail="Already archived")
    event.archived_at = datetime.now(UTC)
    db.commit()
    db.refresh(event)
    logger.info("event_archived", event_id=event.id, actor_id=user.id)
    return _to_out(db, event)


@router.post("/{event_id}/send-feedback-emails", status_code=200)
def send_feedback_emails_now(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> dict[str, int]:
    """Manually trigger the feedback worker for a single event.

    Bypasses the worker's "ended ≥24h ago" cutoff so the organiser can
    send right after the event closes (or whenever they decide). Skips
    signups that have already been processed (anything with
    feedback_sent_at set) — repeated clicks are no-ops once everything
    has been mailed.
    """
    from ..services import feedback_worker

    event = _get_event_scoped(db, event_id, user)
    if not event.questionnaire_enabled:
        raise HTTPException(status_code=409, detail="Questionnaire is disabled for this event")
    processed = feedback_worker.run_for_event(event_id)
    logger.info("feedback_emails_triggered", event_id=event_id, actor_id=user.id, processed=processed)
    return {"processed": processed}


@router.post("/{event_id}/restore", response_model=EventOut)
def restore_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = _get_event_scoped(db, event_id, user)
    if event.archived_at is None:
        raise HTTPException(status_code=409, detail="Not archived")
    event.archived_at = None
    db.commit()
    db.refresh(event)
    logger.info("event_restored", event_id=event.id, actor_id=user.id)
    return _to_out(db, event)


@router.put("/{event_id}", response_model=EventOut)
def update_event(
    event_id: str,
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    """Any approved organiser in the afdeling can edit any event in
    that afdeling — small-org trust model, scoped to the chapter."""
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    event = _get_event_scoped(db, event_id, user)
    event.name = data.name
    event.topic = data.topic
    event.location = data.location
    event.latitude = data.latitude
    event.longitude = data.longitude
    event.starts_at = data.starts_at
    event.ends_at = data.ends_at
    event.source_options = data.source_options
    event.questionnaire_enabled = data.questionnaire_enabled
    db.commit()
    db.refresh(event)
    logger.info("event_updated", event_id=event.id, actor_id=user.id)
    return _to_out(db, event)


@router.get("/by-slug/{slug}", response_model=EventOut)
def get_event_by_slug(slug: str, db: Session = Depends(get_db)) -> EventOut:
    event = (
        db.query(Event)
        .filter(Event.slug == slug, Event.archived_at.is_(None))
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _to_out(db, event)


@router.get("/by-slug/{slug}/qr.png")
def get_event_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    event = (
        db.query(Event)
        .filter(Event.slug == slug, Event.archived_at.is_(None))
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    from qrcode.image.pil import PilImage

    target = f"{PUBLIC_BASE_URL}/e/{event.slug}"
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(target)
    qr.make(fit=True)
    # Black-on-white render via PIL, then re-mode to RGBA and turn
    # every white pixel transparent so the QR drops into posters and
    # flyers without a white box around it.
    pil_img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    img = pil_img.get_image().convert("RGBA")
    pixels = img.load()
    if pixels is not None:
        for y in range(img.height):
            for x in range(img.width):
                px = pixels[x, y]  # type: ignore[index]
                if isinstance(px, tuple) and px[0] == 255 and px[1] == 255 and px[2] == 255:
                    pixels[x, y] = (255, 255, 255, 0)  # type: ignore[index]
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/{event_id}/stats", response_model=EventStatsOut)
def event_stats(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventStatsOut:
    event = _get_event_scoped(db, event_id, user)
    rows = db.query(Signup.source_choice, func.count(Signup.id), func.sum(Signup.party_size)).filter(
        Signup.event_id == event_id
    ).group_by(Signup.source_choice).all()
    total_signups = sum(int(c) for _, c, _ in rows)
    total_attendees = sum(int(s or 0) for _, _, s in rows)
    by_source = {src: int(c) for src, c, _ in rows}
    return EventStatsOut(
        total_signups=total_signups,
        total_attendees=total_attendees,
        by_source=by_source,
    )
