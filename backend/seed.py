"""Startup seeding.

``run_questions()`` always executes — the five fixed questionnaire
questions are global config every install needs, not demo data. It's
idempotent: existing rows are left alone, missing ones are inserted.

``run_local_demo()`` only fires when ``LOCAL_MODE=1`` and seeds the two
test accounts (`admin@local.dev`, `organiser@local.dev`) plus an
upcoming and a past demo event. Never touches real data — the guard is
the env var, not a row count.
"""

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .database import SessionLocal
from .models import (
    EmailChannel,
    EmailStatus,
    Event,
    FeedbackQuestion,
    FeedbackResponse,
    Signup,
    SignupEmailDispatch,
    User,
)
from .services import chapters as chapters_svc
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
    {"ordinal": 3, "kind": "rating", "key": "q3_welcome", "required": True},
    {"ordinal": 4, "kind": "text", "key": "q4_better", "required": False},
    {"ordinal": 5, "kind": "text", "key": "q5_anything_else", "required": False},
]


def _ensure_user(db: Session, *, email: str, name: str, password: str, role: str) -> User:
    from .services import scd2

    user = scd2.current(db.query(User)).filter(User.email == email).first()
    if user:
        return user
    user = scd2.scd2_create(
        db,
        User,
        changed_by="seed",
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=role,
        is_approved=True,
        # Local seed accounts are pre-verified — both gates pass so the
        # account can act immediately.
        email_verified_at=datetime.now(UTC),
        chapter_id=None,
    )
    user.changed_by = user.entity_id  # self-reference once entity_id is known
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
    help_options: list[str],
    chapter_id: str | None,
) -> Event:
    existing = (
        db.query(Event)
        .filter(Event.name == name, Event.created_by == created_by, Event.valid_until.is_(None))
        .first()
    )
    if existing:
        return existing
    from uuid_utils import uuid7
    new_id = str(uuid7())
    now = datetime.now(UTC)
    event = Event(
        id=new_id,
        entity_id=new_id,
        slug=new_slug(),
        name=name,
        topic="Demo",
        location=location,
        starts_at=starts_at,
        ends_at=ends_at,
        source_options=source_options,
        help_options=help_options,
        questionnaire_enabled=True,
        reminder_enabled=True,
        chapter_id=chapter_id,
        created_by=created_by,
        locale="nl",
        valid_from=now,
        valid_until=None,
        changed_by=created_by,
        change_kind="created",
    )
    db.add(event)
    db.flush()
    logger.info("seed_event_created", event_id=event.entity_id, slug=event.slug, name=name)
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
    if not settings.local_mode:
        return

    db = SessionLocal()
    try:
        admin = _ensure_user(db, email=ADMIN_EMAIL, name="Local Admin", password=ADMIN_PASSWORD, role="admin")
        organiser = _ensure_user(
            db,
            email=ORGANISER_EMAIL,
            name="Local Organiser",
            password=ORGANISER_PASSWORD,
            role="organiser",
        )

        # Two demo chapters + one soft-deleted one so the admin
        # autocomplete demonstrates the restore flow on first boot.
        from .services import scd2

        amsterdam = chapters_svc.all_active(db)
        if not any(a.name == "Amsterdam" for a in amsterdam):
            chapters_svc.create(db, name="Amsterdam", changed_by=admin.entity_id)
        if not any(a.name == "Utrecht" for a in chapters_svc.all_active(db)):
            chapters_svc.create(db, name="Utrecht", changed_by=admin.entity_id)
        if not chapters_svc.latest_versions(db, include_archived=True) or not any(
            a.name == "Den Haag"
            for a in chapters_svc.latest_versions(db, include_archived=True)
        ):
            den_haag = chapters_svc.create(db, name="Den Haag", changed_by=admin.entity_id)
            chapters_svc.archive(db, entity_id=den_haag.entity_id, changed_by=admin.entity_id)

        amsterdam_row = next(
            (a for a in chapters_svc.all_active(db) if a.name == "Amsterdam"), None
        )
        amsterdam_id = amsterdam_row.entity_id if amsterdam_row else None

        # Assign the seed admin and organiser to Amsterdam via SCD2-update.
        if admin.chapter_id is None and amsterdam_id:
            admin = scd2.scd2_update(
                db, admin, changed_by=admin.entity_id, chapter_id=amsterdam_id
            )
        if organiser.chapter_id is None and amsterdam_id:
            organiser = scd2.scd2_update(
                db, organiser, changed_by=admin.entity_id, chapter_id=amsterdam_id
            )
        db.flush()

        now = datetime.now(UTC)
        sources = ["Flyer", "Mond-tot-mond", "Social media"]
        help_options = ["Opbouwen", "Afbreken"]

        upcoming = _ensure_event(
            db,
            name="Buurtbijeenkomst Wonen",
            location="Buurthuis Centrum",
            starts_at=now + timedelta(days=3),
            ends_at=now + timedelta(days=3, hours=2),
            created_by=organiser.entity_id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
        )

        past = _ensure_event(
            db,
            name="Demonstratie Klimaatrechtvaardigheid",
            location="Dam, Amsterdam",
            starts_at=now - timedelta(days=2, hours=2),
            ends_at=now - timedelta(days=2),
            created_by=organiser.entity_id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
        )

        # Idempotent demo signups. Upcoming event gets a single
        # not-applicable signup. Past event gets one signup in every
        # feedback-email lifecycle state, so the details page shows
        # the full UX without needing to set up SMTP / wait for the
        # worker.
        def _seed_signup(
            *,
            event_id: str,
            display_name: str,
            party_size: int,
            source: str,
            help_choices: list[str],
            email: str | None = None,
            feedback_status: EmailStatus | None = None,
            feedback_sent_at: datetime | None = None,
            feedback_message_id: str | None = None,
        ) -> None:
            """Insert one demo signup + (optionally) a feedback
            dispatch row matching the requested status."""
            signup = Signup(
                event_id=event_id,
                display_name=display_name,
                party_size=party_size,
                source_choice=source,
                help_choices=help_choices,
                encrypted_email=encryption.encrypt(email)
                if email and feedback_status == EmailStatus.PENDING
                else None,
            )
            db.add(signup)
            db.flush()
            if feedback_status is not None:
                db.add(
                    SignupEmailDispatch(
                        signup_id=signup.id,
                        channel=EmailChannel.FEEDBACK,
                        status=feedback_status,
                        sent_at=feedback_sent_at,
                        message_id=feedback_message_id,
                    )
                )

        if not db.query(Signup).filter(Signup.event_id == upcoming.entity_id).first():
            _seed_signup(
                event_id=upcoming.entity_id,
                display_name="Anon Buur",
                party_size=2,
                source="Flyer",
                help_choices=["Opbouwen"],
            )
        if not db.query(Signup).filter(Signup.event_id == past.entity_id).first():
            # No-email signup: no dispatch row at all.
            _seed_signup(
                event_id=past.entity_id,
                display_name="Demo Anon",
                party_size=1,
                source="Social media",
                help_choices=["Opbouwen", "Afbreken"],
            )
            # pending: still ciphertext on disk, worker hasn't run yet.
            _seed_signup(
                event_id=past.entity_id,
                display_name="Pim",
                party_size=1,
                source="Flyer",
                help_choices=["Afbreken"],
                email="pim@local.dev",
                feedback_status=EmailStatus.PENDING,
            )
            # sent: worker successfully handed the message to SMTP.
            _seed_signup(
                event_id=past.entity_id,
                display_name="Sien",
                party_size=2,
                source="Mond-tot-mond",
                help_choices=["Opbouwen"],
                feedback_status=EmailStatus.SENT,
                feedback_sent_at=now - timedelta(days=1, hours=23),
                feedback_message_id="<demo-sent@local.dev>",
            )
            # bounced: webhook flagged a hard delivery failure.
            _seed_signup(
                event_id=past.entity_id,
                display_name="Robin",
                party_size=1,
                source="Social media",
                help_choices=[],
                feedback_status=EmailStatus.BOUNCED,
                feedback_sent_at=now - timedelta(days=1, hours=22),
                feedback_message_id="<demo-bounced@local.dev>",
            )
            # complaint: recipient flagged it as spam.
            _seed_signup(
                event_id=past.entity_id,
                display_name="Kees",
                party_size=1,
                source="Flyer",
                help_choices=["Opbouwen", "Afbreken"],
                feedback_status=EmailStatus.COMPLAINT,
                feedback_sent_at=now - timedelta(days=1, hours=21),
                feedback_message_id="<demo-complaint@local.dev>",
            )
            # failed: SMTP rejected after retries.
            _seed_signup(
                event_id=past.entity_id,
                display_name="Mira",
                party_size=3,
                source="Mond-tot-mond",
                help_choices=["Afbreken"],
                feedback_status=EmailStatus.FAILED,
                feedback_sent_at=now - timedelta(days=1, hours=20),
            )

        # Sample filled-in questionnaires on the past event so the stats
        # page has something to render. Idempotent: only seed if there
        # are no responses yet for this event.
        existing_resp = (
            db.query(FeedbackResponse).filter(FeedbackResponse.event_id == past.entity_id).first()
        )
        if existing_resp is None:
            _seed_demo_responses(db, past.entity_id)

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
