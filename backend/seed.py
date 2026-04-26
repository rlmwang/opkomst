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
import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from .auth import hash_password
from .database import SessionLocal
from .models import Event, FeedbackQuestion, FeedbackResponse, Signup, User
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
        # Local seed accounts are pre-verified — both gates pass so the
        # account can act immediately.
        email_verified_at=datetime.now(UTC),
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

        # Idempotent demo signups. Upcoming event gets a single
        # not-applicable signup. Past event gets one signup in every
        # feedback-email lifecycle state, so the details page shows
        # the full UX without needing to set up SMTP / wait for the
        # worker.
        if not db.query(Signup).filter(Signup.event_id == upcoming.id).first():
            db.add(
                Signup(
                    event_id=upcoming.id,
                    display_name="Anon Buur",
                    party_size=2,
                    source_choice="Flyer",
                    encrypted_email=None,
                    feedback_email_status="not_applicable",
                )
            )
        if not db.query(Signup).filter(Signup.event_id == past.id).first():
            # not_applicable: someone signed up without an email.
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Demo Anon",
                    party_size=1,
                    source_choice="Social media",
                    encrypted_email=None,
                    feedback_email_status="not_applicable",
                )
            )
            # pending: still ciphertext on disk, worker hasn't run yet
            # (in real life this lasts until the next hourly tick).
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Pim",
                    party_size=1,
                    source_choice="Flyer",
                    encrypted_email=encryption.encrypt("pim@local.dev"),
                    feedback_email_status="pending",
                )
            )
            # sent: worker successfully handed the message to SMTP.
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Sien",
                    party_size=2,
                    source_choice="Mond-tot-mond",
                    encrypted_email=None,
                    feedback_email_status="sent",
                    feedback_sent_at=now - timedelta(days=1, hours=23),
                    feedback_message_id="<demo-sent@local.dev>",
                )
            )
            # bounced: TEM webhook reported the address as
            # undeliverable after a successful send.
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Robin",
                    party_size=1,
                    source_choice="Social media",
                    encrypted_email=None,
                    feedback_email_status="bounced",
                    feedback_sent_at=now - timedelta(days=1, hours=22),
                    feedback_message_id="<demo-bounced@local.dev>",
                )
            )
            # complaint: recipient flagged it as spam. Rare but the UI
            # should distinguish it from a bounce.
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Kees",
                    party_size=1,
                    source_choice="Flyer",
                    encrypted_email=None,
                    feedback_email_status="complaint",
                    feedback_sent_at=now - timedelta(days=1, hours=21),
                    feedback_message_id="<demo-complaint@local.dev>",
                )
            )
            # failed: SMTP send threw after retry, or decrypt failed.
            db.add(
                Signup(
                    event_id=past.id,
                    display_name="Mira",
                    party_size=3,
                    source_choice="Mond-tot-mond",
                    encrypted_email=None,
                    feedback_email_status="failed",
                    feedback_sent_at=now - timedelta(days=1, hours=20),
                    feedback_message_id=None,
                )
            )

        # Sample filled-in questionnaires on the past event so the stats
        # page has something to render. Idempotent: only seed if there
        # are no responses yet for this event.
        existing_resp = (
            db.query(FeedbackResponse).filter(FeedbackResponse.event_id == past.id).first()
        )
        if existing_resp is None:
            _seed_demo_responses(db, past.id)

        db.commit()
        logger.info("seed_complete")
    finally:
        db.close()


# Six fictional responses on the past event. Mix of ratings and
# texts so every chart on the stats page lights up. The submission
# ids are random so they look like real ones.
_DEMO_SUBMISSIONS = [
    {"q1_overall": 5, "q2_recommend": 5, "q3_welcome": 5,
     "q4_better": "Ietsje meer ruimte vooraan voor mensen die slecht horen.",
     "q5_anything_else": "Bedankt voor het organiseren!"},
    {"q1_overall": 4, "q2_recommend": 5, "q3_welcome": 4,
     "q4_better": "De aankondiging mocht een week eerder.",
     "q5_anything_else": None},
    {"q1_overall": 4, "q2_recommend": 4, "q3_welcome": 5,
     "q4_better": None,
     "q5_anything_else": "Volgende keer graag een vegan optie bij de soep."},
    {"q1_overall": 3, "q2_recommend": 3, "q3_welcome": 4,
     "q4_better": "De zaal was warm. Ramen open zou helpen.",
     "q5_anything_else": None},
    {"q1_overall": 5, "q2_recommend": 5, "q3_welcome": None,
     "q4_better": None,
     "q5_anything_else": None},
    {"q1_overall": 2, "q2_recommend": 3, "q3_welcome": 2,
     "q4_better": "Het hoofdverhaal duurde te lang. Korter en feller volgende keer.",
     "q5_anything_else": "Geluid was af en toe niet goed te volgen."},
]


def _seed_demo_responses(db: Session, event_id: str) -> None:
    questions = {q.key: q for q in db.query(FeedbackQuestion).all()}
    for submission in _DEMO_SUBMISSIONS:
        sub_id = secrets.token_urlsafe(16)
        for key, value in submission.items():
            if value is None:
                continue
            q = questions.get(key)
            if not q:
                continue
            db.add(
                FeedbackResponse(
                    event_id=event_id,
                    question_id=q.id,
                    submission_id=sub_id,
                    answer_int=value if isinstance(value, int) else None,
                    answer_text=value if isinstance(value, str) else None,
                )
            )
    logger.info("seed_demo_feedback", event_id=event_id, count=len(_DEMO_SUBMISSIONS))


def run() -> None:
    """Run all seed steps. Called from main.py at startup."""
    run_questions()
    run_local_demo()
