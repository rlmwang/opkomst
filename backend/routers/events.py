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
        signup_count=_attendees_for(db, event.id),
    )


@router.post("", response_model=EventOut, status_code=201)
def create_event(
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
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
    _user: User = Depends(require_approved),
) -> list[EventOut]:
    """Every approved organiser sees every active event — small-org trust model."""
    rows = (
        db.query(Event)
        .filter(Event.archived_at.is_(None))
        .order_by(Event.starts_at.desc())
        .all()
    )
    return [_to_out(db, e) for e in rows]


@router.get("/archived", response_model=list[EventOut])
def list_archived_events(
    db: Session = Depends(get_db),
    _user: User = Depends(require_approved),
) -> list[EventOut]:
    """Archived events — only visible to approved organisers. Restore
    flips them back to active."""
    rows = (
        db.query(Event)
        .filter(Event.archived_at.is_not(None))
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

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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
    """Any approved organiser can edit any event — small-org trust model."""
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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
    _user: User = Depends(require_approved),
) -> EventStatsOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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
