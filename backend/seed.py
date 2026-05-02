"""Startup seeding — local demo data only.

``run_local_demo()`` fires via ``python -m backend.cli seed-demo``
when ``LOCAL_MODE=1`` is set. It seeds the two test accounts
(``admin@local.dev``, ``organiser@local.dev``) plus an upcoming
and a past demo event. The CLI subcommand refuses to run in any
other environment, so a stray invocation against prod can't
fabricate fake users.

The fixed-set feedback questions are NOT seeded — they live as
Python constants in ``services.feedback_questions``. There is no
``feedback_questions`` table and no row to insert.
"""

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import (
    Chapter,
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Event,
    FeedbackResponse,
    Signup,
    User,
)
from .services import chapters as chapters_svc
from .services import encryption
from .services import user_chapters as user_chapters_svc
from .services.slug import new_slug

logger = structlog.get_logger()

ADMIN_EMAIL = "admin@local.dev"
ORGANISER_EMAIL = "organiser@local.dev"


def _ensure_user(db: Session, *, email: str, name: str, role: str) -> User:
    user = db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()
    if user:
        return user
    user = User(email=email, name=name, role=role, is_approved=True)
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
    help_options: list[str],
    chapter_id: str | None,
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
        help_options=help_options,
        feedback_enabled=True,
        reminder_enabled=True,
        chapter_id=chapter_id,
        created_by=created_by,
        locale="nl",
    )
    db.add(event)
    db.flush()
    logger.info("seed_event_created", event_id=event.id, slug=event.slug, name=name)
    return event


def run_local_demo() -> None:
    """Insert the two demo accounts + upcoming/past demo events.
    Idempotent. Refuses to run unless ``LOCAL_MODE=1`` so a stray
    ``cli seed-demo`` against prod can't fabricate user rows."""
    if not settings.local_mode:
        raise SystemExit("seed-demo refused: LOCAL_MODE is not 1 (would seed fake users into a non-local DB)")

    db = SessionLocal()
    try:
        admin = _ensure_user(db, email=ADMIN_EMAIL, name="Local Admin", role="admin")
        organiser = _ensure_user(
            db,
            email=ORGANISER_EMAIL,
            name="Local Organiser",
            role="organiser",
        )

        # Two demo chapters + one soft-deleted one so the admin
        # autocomplete demonstrates the restore flow on first boot.
        active_names = {c.name for c in chapters_svc.all_active(db)}
        if "Amsterdam" not in active_names:
            chapters_svc.create(db, name="Amsterdam")
        if "Utrecht" not in active_names:
            chapters_svc.create(db, name="Utrecht")
        all_names = {c.name for c in chapters_svc.latest_versions(db, include_archived=True)}
        if "Den Haag" not in all_names:
            den_haag = chapters_svc.create(db, name="Den Haag")
            db.flush()
            chapters_svc.archive(db, chapter_id=den_haag.id)

        amsterdam_row = db.query(Chapter).filter(Chapter.name == "Amsterdam", Chapter.deleted_at.is_(None)).first()
        amsterdam_id = amsterdam_row.id if amsterdam_row else None

        # Multi-chapter membership lives in ``user_chapters``; the
        # helper is idempotent so re-seeding doesn't duplicate
        # rows. The organiser also gets Utrecht so the local
        # frontend has a real two-chapter dataset to render the
        # filter dropdown against.
        utrecht_row = db.query(Chapter).filter(Chapter.name == "Utrecht", Chapter.deleted_at.is_(None)).first()
        utrecht_id = utrecht_row.id if utrecht_row else None
        if amsterdam_id:
            user_chapters_svc.add_to_chapter(db, admin.id, amsterdam_id)
            user_chapters_svc.add_to_chapter(db, organiser.id, amsterdam_id)
        if utrecht_id:
            user_chapters_svc.add_to_chapter(db, organiser.id, utrecht_id)
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
            created_by=organiser.id,
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
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
        )

        # Idempotent demo signups. Past event gets one signup in
        # every feedback-email lifecycle state, so the details
        # page shows the full UX without needing real SMTP.
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
            signup = Signup(
                event_id=event_id,
                display_name=display_name,
                party_size=party_size,
                source_choice=source,
                help_choices=help_choices,
            )
            db.add(signup)
            if feedback_status is not None:
                # Pending dispatches carry the encrypted address;
                # terminal-state rows have it nulled (matches the
                # production lifecycle). The dispatch row points
                # at the event directly — no link to this signup.
                ciphertext = encryption.encrypt(email) if email and feedback_status == EmailStatus.PENDING else None
                db.add(
                    EmailDispatch(
                        event_id=event_id,
                        channel=EmailChannel.FEEDBACK,
                        status=feedback_status,
                        sent_at=feedback_sent_at,
                        message_id=feedback_message_id,
                        encrypted_email=ciphertext,
                    )
                )

        if not db.query(Signup).filter(Signup.event_id == upcoming.id).first():
            _seed_signup(
                event_id=upcoming.id,
                display_name="Anon Buur",
                party_size=2,
                source="Flyer",
                help_choices=["Opbouwen"],
            )
        if not db.query(Signup).filter(Signup.event_id == past.id).first():
            _seed_signup(
                event_id=past.id,
                display_name="Demo Anon",
                party_size=1,
                source="Social media",
                help_choices=["Opbouwen", "Afbreken"],
            )
            _seed_signup(
                event_id=past.id,
                display_name="Pim",
                party_size=1,
                source="Flyer",
                help_choices=["Afbreken"],
                email="pim@local.dev",
                feedback_status=EmailStatus.PENDING,
            )
            _seed_signup(
                event_id=past.id,
                display_name="Sien",
                party_size=2,
                source="Mond-tot-mond",
                help_choices=["Opbouwen"],
                feedback_status=EmailStatus.SENT,
                feedback_sent_at=now - timedelta(days=1, hours=23),
                feedback_message_id="<demo-sent@local.dev>",
            )
            _seed_signup(
                event_id=past.id,
                display_name="Mira",
                party_size=3,
                source="Mond-tot-mond",
                help_choices=["Afbreken"],
                feedback_status=EmailStatus.FAILED,
                feedback_sent_at=now - timedelta(days=1, hours=20),
            )

        existing_resp = db.query(FeedbackResponse).filter(FeedbackResponse.event_id == past.id).first()
        if existing_resp is None:
            _seed_demo_responses(db, past.id)

        db.commit()
        logger.info("seed_complete")
    finally:
        db.close()


_DEMO_SUBMISSIONS = [
    {
        "q1_overall": 5,
        "q2_recommend": 5,
        "q3_welcome": 5,
        "q4_better": "Ietsje meer ruimte vooraan voor mensen die slecht horen.",
        "q5_anything_else": "Bedankt voor het organiseren!",
    },
    {
        "q1_overall": 4,
        "q2_recommend": 5,
        "q3_welcome": 4,
        "q4_better": "De aankondiging mocht een week eerder.",
        "q5_anything_else": None,
    },
    {
        "q1_overall": 4,
        "q2_recommend": 4,
        "q3_welcome": 5,
        "q4_better": None,
        "q5_anything_else": "Volgende keer graag een vegan optie bij de soep.",
    },
    {
        "q1_overall": 3,
        "q2_recommend": 3,
        "q3_welcome": 4,
        "q4_better": "De zaal was warm. Ramen open zou helpen.",
        "q5_anything_else": None,
    },
    {"q1_overall": 5, "q2_recommend": 5, "q3_welcome": None, "q4_better": None, "q5_anything_else": None},
    {
        "q1_overall": 2,
        "q2_recommend": 3,
        "q3_welcome": 2,
        "q4_better": "Het hoofdverhaal duurde te lang. Korter en feller volgende keer.",
        "q5_anything_else": "Geluid was af en toe niet goed te volgen.",
    },
]


def _seed_demo_responses(db: Session, event_id: str) -> None:
    from .services.feedback_questions import BY_KEY

    for submission in _DEMO_SUBMISSIONS:
        sub_id = secrets.token_urlsafe(16)
        for key, value in submission.items():
            if value is None:
                continue
            if key not in BY_KEY:
                continue
            db.add(
                FeedbackResponse(
                    event_id=event_id,
                    question_key=key,
                    submission_id=sub_id,
                    answer_int=value if isinstance(value, int) else None,
                    answer_text=value if isinstance(value, str) else None,
                )
            )
    logger.info("seed_demo_feedback", event_id=event_id, count=len(_DEMO_SUBMISSIONS))
