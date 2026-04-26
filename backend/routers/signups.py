import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Event, Signup
from ..schemas.events import SignupAck, SignupCreate
from ..services import encryption

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["signups"])


@router.post("/by-slug/{slug}/signups", response_model=SignupAck, status_code=201)
def create_signup(slug: str, data: SignupCreate, db: Session = Depends(get_db)) -> SignupAck:
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if data.source_choice not in event.source_options:
        raise HTTPException(status_code=400, detail="source_choice must match one of the event's options")

    # When the questionnaire is off (or no email was provided) the
    # signup is "not_applicable" — feedback worker will never look at
    # it. Otherwise it's "pending" until the worker runs.
    has_email = bool(data.email) and event.questionnaire_enabled
    encrypted = encryption.encrypt(data.email) if has_email and data.email else None
    signup = Signup(
        event_id=event.id,
        display_name=data.display_name,
        party_size=data.party_size,
        source_choice=data.source_choice,
        encrypted_email=encrypted,
        feedback_email_status="pending" if has_email else "not_applicable",
    )
    db.add(signup)
    db.commit()
    # Note: log only the event id and party size — never the display name or email.
    logger.info("signup_created", event_id=event.id, party_size=data.party_size)
    return SignupAck()
