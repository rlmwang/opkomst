"""Startup seeding.

``run_questions()`` always executes — the five fixed questionnaire
questions are global config every install needs, not demo data. It's
idempotent: existing rows are left alone, missing ones are inserted.

``run_local_demo()`` only fires when ``LOCAL_MODE=1`` and seeds the two
test accounts (`admin@local.dev`, `organiser@local.dev`) plus an
upcoming and a past demo event. Never touches real data — the guard is
the env var, not a row count.
"""

import os
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from .auth import hash_password
from .database import SessionLocal
from .models import Event, FeedbackQuestion, Signup, User
from .services import encryption
from .services.slug import new_slug

logger = structlog.get_logger()

ADMIN_EMAIL = "admin@local.dev"
ADMIN_PASSWORD = "admin1234"
ORGANISER_EMAIL = "organiser@local.dev"
ORGANISER_PASSWORD = "organiser1234"


# Single source of truth for the post-event questionnaire. Five
# questions, ~60–90s — designed to land in the 80%+ completion bracket
# (1–3 questions = 83% completion per NIH / SurveyMonkey research).
# Q1 anchors a comparable CSAT across events, Q2 is the
# recommendation question, Q3 is the welcoming-specific check, Q4–Q5
# are diagnostic open boxes.
SEED_QUESTIONS = [
    {"ordinal": 1, "kind": "rating", "key": "q1_overall", "required": True},
    {"ordinal": 2, "kind": "rating", "key": "q2_recommend", "required": True},
    {"ordinal": 3, "kind": "rating", "key": "q3_welcome", "required": False},
    {"ordinal": 4, "kind": "text", "key": "q4_better", "required": False},
    {"ordinal": 5, "kind": "text", "key": "q5_anything_else", "required": False},
]


def _ensure_user(db: Session, *, email: str, name: str, password: str, role: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=role,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    logger.info("seed_user_created", email=email, role=role)
    return user


def _ensure_event(
    db: Session,
    *,
    name: str,
    location: str,
    starts_at: datetime,
    ends_at: datetime,
    created_by: str,
    source_options: list[str],
) -> Event:
    existing = db.query(Event).filter(Event.name == name, Event.created_by == created_by).first()
    if existing:
        return existing
    event = Event(
        slug=new_slug(),
        name=name,
        topic="Demo",
        location=location,
        starts_at=starts_at,
        ends_at=ends_at,
        source_options=source_options,
        created_by=created_by,
    )
    db.add(event)
    db.flush()
    logger.info("seed_event_created", event_id=event.id, slug=event.slug, name=name)
    return event


def run_questions() -> None:
    """Always-on seed. Inserts the five fixed feedback questions if missing."""
    db = SessionLocal()
    try:
        for spec in SEED_QUESTIONS:
            existing = db.query(FeedbackQuestion).filter(FeedbackQuestion.key == spec["key"]).first()
            if existing:
                continue
            db.add(FeedbackQuestion(**spec))
        db.commit()
    finally:
        db.close()


def run_local_demo() -> None:
    if os.environ.get("LOCAL_MODE") != "1":
        return

    db = SessionLocal()
    try:
        _ensure_user(db, email=ADMIN_EMAIL, name="Local Admin", password=ADMIN_PASSWORD, role="admin")
        organiser = _ensure_user(
            db,
            email=ORGANISER_EMAIL,
            name="Local Organiser",
            password=ORGANISER_PASSWORD,
            role="organiser",
        )

        now = datetime.now(UTC)
        sources = ["Flyer", "Mond-tot-mond", "Social media"]

        upcoming = _ensure_event(
            db,
            name="Buurtbijeenkomst Wonen",
            location="Buurthuis Centrum",
            starts_at=now + timedelta(days=3),
            ends_at=now + timedelta(days=3, hours=2),
            created_by=organiser.id,
            source_options=sources,
        )

        past = _ensure_event(
            db,
            name="Demonstratie Klimaatrechtvaardigheid",
            location="Dam, Amsterdam",
            starts_at=now - timedelta(days=2, hours=2),
            ends_at=now - timedelta(days=2),
            created_by=organiser.id,
            source_options=sources,
        )

        # One signup on each event, the past one with an encrypted email
        # so the feedback worker has something real to process on the
        # next hourly tick. Idempotent: only insert if the event has no
        # signups yet.
        if not db.query(Signup).filter(Signup.event_id == upcoming.id).first():
            db.add(
                Signup(
                    event_id=upcoming.id,
                    display_name="Anon Buur",
                    party_size=2,
                    source_choice="Flyer",
                    encrypted_email=None,
                )
            )
        if not db.query(Signup).filter(Signup.event_id == past.id).first():
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Demo Anon",
                    party_size=1,
                    source_choice="Social media",
                    encrypted_email=encryption.encrypt("feedback-target@local.dev"),
                )
            )

        db.commit()
        logger.info("seed_complete")
    finally:
        db.close()


def run() -> None:
    """Run all seed steps. Called from main.py at startup."""
    run_questions()
    run_local_demo()
