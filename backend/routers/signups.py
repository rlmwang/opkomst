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
    if data.source_choice not in event.source_options:
        raise HTTPException(status_code=400, detail="source_choice must match one of the event's options")

    has_email = bool(data.email) and event.questionnaire_enabled
    encrypted = encryption.encrypt(data.email) if has_email and data.email else None
    signup = Signup(
        # Point at the stable logical id so signups survive every edit.
        event_id=event.entity_id,
        display_name=data.display_name,
        party_size=data.party_size,
        source_choice=data.source_choice,
        encrypted_email=encrypted,
        feedback_email_status="pending" if has_email else "not_applicable",
    )
    db.add(signup)
    db.commit()
    logger.info("signup_created", event_id=event.entity_id, party_size=data.party_size)
    return SignupAck()
