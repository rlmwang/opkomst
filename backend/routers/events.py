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
        created_by=user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info("event_created", event_id=event.id, actor_id=user.id)
    return _to_out(db, event)


@router.get("/mine", response_model=list[EventOut])
def list_my_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    rows = db.query(Event).filter(Event.created_by == user.id).order_by(Event.starts_at.desc()).all()
    return [_to_out(db, e) for e in rows]


@router.get("/by-slug/{slug}", response_model=EventOut)
def get_event_by_slug(slug: str, db: Session = Depends(get_db)) -> EventOut:
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _to_out(db, event)


@router.get("/by-slug/{slug}/qr.png")
def get_event_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    target = f"{PUBLIC_BASE_URL}/e/{event.slug}"
    img = qrcode.make(target, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/{event_id}/stats", response_model=EventStatsOut)
def event_stats(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventStatsOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
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
