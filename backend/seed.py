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
from datetime import date, datetime, time, timedelta

import structlog
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import (
    Chapter,
    Chore,
    Datepoll,
    DatepollResponse,
    DatepollSlot,
    DatepollSubmission,
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Enrollment,
    Event,
    FeedbackResponse,
    Form,
    FormQuestion,
    FormResponse,
    FormSubmission,
    Occurrence,
    Registration,
    Roster,
    Shift,
    ShiftEvent,
    Signup,
    User,
    Volunteer,
    VolunteerAvailability,
)
from .services import chapters as chapters_svc
from .services import chore_tick, edit_token, encryption, event_recurrence, tenancy
from .services import tenants as tenants_svc
from .services import user_chapters as user_chapters_svc
from .services.events import now_wallclock
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
    first_starts_at: datetime,
    first_ends_at: datetime,
    created_by: str,
    source_options: list[str],
    help_options: list[str],
    chapter_id: str | None,
    topic: str = "Demo",
    name_en: str | None = None,
    topic_en: str | None = None,
    weekly_weeks: int | None = None,
) -> Event:
    """Create a demo event and materialise its in-horizon occurrences. The
    date + times of ``first_starts_at`` / ``first_ends_at`` become the
    anchor + time of day. Defaults to a one-off; pass ``weekly_weeks`` for a
    weekly demo course running that many weeks (on the anchor's weekday).
    Idempotent on ``(name, created_by)``."""
    existing = db.query(Event).filter(Event.name_nl == name, Event.created_by == created_by).first()
    if existing:
        return existing
    starts_on = first_starts_at.date()
    cycle_slots = [starts_on.weekday()] if weekly_weeks else []
    event = Event(
        slug=new_slug(),
        name_nl=name,
        name_en=name_en,
        topic_nl=topic,
        topic_en=topic_en,
        location=location,
        starts_on=starts_on,
        start_time=first_starts_at.time(),
        end_time=first_ends_at.time(),
        period_weeks=1,
        cycle_slots=cycle_slots,
        span_weeks=weekly_weeks,
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
    # Back-fill past sessions too, so a demo course that straddles "now" (and
    # the past demo events) have believable history on first boot. Production
    # never fabricates past occurrences.
    event_recurrence.materialise(db, event, now_wallclock(), include_past=True)
    logger.info("seed_event_created", event_id=event.id, slug=event.slug, name=name)
    return event


def _first_occurrence(event: Event) -> Occurrence:
    """The demo events materialise occurrence 0 immediately, so this is
    always present right after ``_ensure_event``."""
    return min(event.occurrences, key=lambda o: o.starts_at)


def run_local_demo() -> None:
    """Insert the two demo accounts + upcoming/past demo events.
    Idempotent. Refuses to run unless ``LOCAL_MODE=1`` so a stray
    ``cli seed-demo`` against prod can't fabricate user rows."""
    if not settings.local_mode:
        raise SystemExit("seed-demo refused: LOCAL_MODE is not 1 (would seed fake users into a non-local DB)")

    db = SessionLocal()
    try:
        # Everything below belongs to one organisation — the first one
        # ``TENANTS`` lists. The CLI reconciles the table before any
        # subcommand runs, so it is already there.
        tenant = tenants_svc.list_live(db)[0]
        tenancy.bind(tenant.id, tenant.slug)

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

        # ``now_wallclock()`` is the wall-clock frame ``Event.starts_at``
        # lives in. ``datetime.now(UTC)`` would land seeded demo
        # events two hours off (the bug the lifecycle docstrings now
        # call out by name).
        now = now_wallclock()
        sources = ["Flyer", "Mond-tot-mond", "Social media"]
        help_options = ["Opbouwen", "Afbreken"]

        upcoming = _ensure_event(
            db,
            name="Buurtbijeenkomst Wonen",
            location="Buurthuis Centrum",
            first_starts_at=now + timedelta(days=3),
            first_ends_at=now + timedelta(days=3, hours=2),
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
        )

        past = _ensure_event(
            db,
            name="Demonstratie Klimaatrechtvaardigheid",
            location="Dam, Amsterdam",
            first_starts_at=now - timedelta(days=2, hours=2),
            first_ends_at=now - timedelta(days=2),
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
        )

        # A couple more upcoming events so the public chapter agenda
        # (``/e/amsterdam``) renders a populated grid on first boot.
        # No image_url on these, so they show the muted-RSP-logo default.
        _ensure_event(
            db,
            name="Ledenvergadering",
            name_en="Members' meeting",
            location="Volkshuis, Amsterdam-Oost",
            first_starts_at=now + timedelta(days=10),
            first_ends_at=now + timedelta(days=10, hours=2),
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
            topic="Bespreek de plannen voor het najaar en kies de nieuwe werkgroepcoördinatoren.",
            topic_en="Discuss the autumn plans and elect the new working-group coordinators.",
        )
        _ensure_event(
            db,
            name="Scholingsavond: organiseren op je werk",
            location="De Nieuwe Liefde, Amsterdam",
            first_starts_at=now + timedelta(days=18),
            first_ends_at=now + timedelta(days=18, hours=3),
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
            topic="Een praktische avond over hoe je collega's mee krijgt in actie.",
        )
        # An unlisted upcoming event: reachable by link, hidden from the
        # agenda — demonstrates the ``listed`` toggle.
        hidden = _ensure_event(
            db,
            name="Besloten werkgroepoverleg",
            location="Online",
            first_starts_at=now + timedelta(days=5),
            first_ends_at=now + timedelta(days=5, hours=1),
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
            topic="Intern overleg, niet op de agenda.",
        )
        hidden.listed = False
        db.flush()

        # A recurring course (six weekly sessions) that straddles "now": it
        # started ~2.5 weeks ago, so the first three sessions are in the past
        # (frozen history) and the last three are still upcoming. This gives
        # the local frontend a real multi-occurrence dataset that exercises
        # both states everywhere: the agenda shows the next couple of upcoming
        # sessions, the detail page's calendar has past + future days, and the
        # public sign-up / manage calendar shows editable-future alongside
        # locked-past cells.
        course_anchor = (now - timedelta(days=17)).replace(hour=19, minute=0, second=0, microsecond=0)
        course = _ensure_event(
            db,
            name="Boksles voor beginners",
            location="Sporthal De Kaai, Amsterdam",
            first_starts_at=course_anchor,
            first_ends_at=course_anchor.replace(hour=20, minute=30),
            created_by=organiser.id,
            source_options=sources,
            help_options=help_options,
            chapter_id=amsterdam_id,
            topic="Zes wekelijkse lessen. Schrijf je in voor de hele reeks of losse lessen.",
            weekly_weeks=6,
        )

        # Utrecht gets its own events so the second chapter's agenda
        # (``/e/utrecht``) isn't empty on first boot.
        if utrecht_id:
            _ensure_event(
                db,
                name="Kennismaking nieuwe leden",
                location="Buurthuis Lombok, Utrecht",
                first_starts_at=now + timedelta(days=7),
                first_ends_at=now + timedelta(days=7, hours=2),
                created_by=organiser.id,
                source_options=sources,
                help_options=help_options,
                chapter_id=utrecht_id,
                topic="Welkom! Maak kennis met de afdeling en de lopende campagnes.",
            )
            _ensure_event(
                db,
                name="Buurtactie tegen de huurverhoging",
                location="Kanaalstraat, Utrecht",
                first_starts_at=now - timedelta(days=4, hours=2),
                first_ends_at=now - timedelta(days=4),
                created_by=organiser.id,
                source_options=sources,
                help_options=help_options,
                chapter_id=utrecht_id,
                topic="Terugblik op de deur-aan-deur actie in Lombok.",
            )

        # Idempotent demo signups. Each is a booking (registration) with one
        # line item on the given occurrence. The past event gets one signup in
        # every feedback-email lifecycle state, so the details page shows the
        # full UX without needing real SMTP.
        def _seed_signup(
            *,
            occurrence_id: str,
            display_name: str,
            party_size: int,
            source: str,
            help_choices: list[str],
            email: str | None = None,
            feedback_status: EmailStatus | None = None,
            feedback_sent_at: datetime | None = None,
            feedback_message_id: str | None = None,
        ) -> None:
            _, token_hash = edit_token.new_edit_token()
            registration = Registration(
                event_id=db.query(Occurrence.event_id).filter(Occurrence.id == occurrence_id).scalar(),
                display_name=display_name,
                party_size=party_size,
                edit_token_hash=token_hash,
            )
            db.add(registration)
            db.flush()
            db.add(
                Signup(
                    registration_id=registration.id,
                    occurrence_id=occurrence_id,
                    source_choice=source,
                    help_choices=help_choices,
                )
            )
            if feedback_status is not None:
                # Pending dispatches carry the encrypted address; terminal-state
                # rows have it nulled (matches the production lifecycle). The
                # dispatch row points at the occurrence directly — no link to
                # the booking or line item.
                ciphertext = encryption.encrypt(email) if email and feedback_status == EmailStatus.PENDING else None
                db.add(
                    EmailDispatch(
                        occurrence_id=occurrence_id,
                        channel=EmailChannel.FEEDBACK,
                        status=feedback_status,
                        sent_at=feedback_sent_at,
                        message_id=feedback_message_id,
                        encrypted_email=ciphertext,
                    )
                )

        upcoming_occ = _first_occurrence(upcoming)
        past_occ = _first_occurrence(past)
        if not db.query(Signup).filter(Signup.occurrence_id == upcoming_occ.id).first():
            _seed_signup(
                occurrence_id=upcoming_occ.id,
                display_name="Anon Buur",
                party_size=2,
                source="Flyer",
                help_choices=["Opbouwen"],
            )
        if not db.query(Signup).filter(Signup.occurrence_id == past_occ.id).first():
            _seed_signup(
                occurrence_id=past_occ.id,
                display_name="Demo Anon",
                party_size=1,
                source="Social media",
                help_choices=["Opbouwen", "Afbreken"],
            )
            _seed_signup(
                occurrence_id=past_occ.id,
                display_name="Pim",
                party_size=1,
                source="Flyer",
                help_choices=["Afbreken"],
                email="pim@local.dev",
                feedback_status=EmailStatus.PENDING,
            )
            _seed_signup(
                occurrence_id=past_occ.id,
                display_name="Sien",
                party_size=2,
                source="Mond-tot-mond",
                help_choices=["Opbouwen"],
                feedback_status=EmailStatus.SENT,
                feedback_sent_at=now - timedelta(days=1, hours=23),
                feedback_message_id="<demo-sent@local.dev>",
            )
            _seed_signup(
                occurrence_id=past_occ.id,
                display_name="Mira",
                party_size=3,
                source="Mond-tot-mond",
                help_choices=["Afbreken"],
                feedback_status=EmailStatus.FAILED,
                feedback_sent_at=now - timedelta(days=1, hours=20),
            )

        existing_resp = db.query(FeedbackResponse).filter(FeedbackResponse.occurrence_id == past_occ.id).first()
        if existing_resp is None:
            _seed_demo_responses(db, past_occ.id)

        # A multi-occurrence booking that spans the "now" line: this person is
        # on the course's middle four sessions (two already past, two still
        # upcoming), so the manage page (secret edit link) showcases both
        # locked-past sessions and editable-future ones at once.
        course_occs = sorted(course.occurrences, key=lambda o: o.starts_at)[1:5]
        if course_occs and not db.query(Signup).filter(Signup.occurrence_id == course_occs[0].id).first():
            _, course_token = edit_token.new_edit_token()
            course_reg = Registration(
                event_id=course.id, display_name="Vaste ganger", party_size=1, edit_token_hash=course_token
            )
            db.add(course_reg)
            db.flush()
            for occ in course_occs:
                db.add(
                    Signup(
                        registration_id=course_reg.id,
                        occurrence_id=occ.id,
                        source_choice="Social media",
                        help_choices=[],
                    )
                )

        _seed_rosters(db, created_by=organiser.id, chapter_id=amsterdam_id, now=now)
        _seed_forms(db, created_by=organiser.id, chapter_id=amsterdam_id, now=now)
        _seed_datepolls(db, created_by=organiser.id, chapter_id=amsterdam_id, now=now)

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


def _seed_rosters(db: Session, *, created_by: str, chapter_id: str | None, now: datetime) -> None:
    """Three demo chore rosters, one per lifecycle state, so the details /
    list / archived pages all have something real to render locally:

    * **forming** — a draft roster (``activated_at`` NULL): chores + a
      couple of enrolments, but nothing scheduled yet.
    * **running** — activated a fortnight ago: multiple chores, four
      volunteers (one with a reminder email, one away next weekend), a
      week of completed/missed history feeding the accountability tally,
      and a pinned upcoming week (incl. one open slot).
    * **archived** — a finished, archived campaign with completion history.

    Idempotent: each roster is keyed on ``(name, created_by)`` and skipped
    if already present.
    """
    today = now.date()

    def wd(weekday: int, week_offset: int) -> date:
        """Date of ``weekday`` (Mon=0) in the week ``week_offset`` from now."""
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(weeks=week_offset, days=weekday)

    def _roster(name: str, **kw: object) -> Roster | None:
        if db.query(Roster).filter(Roster.name_nl == name, Roster.created_by == created_by).first():
            return None  # already seeded
        roster = Roster(slug=new_slug(), name_nl=name, created_by=created_by, chapter_id=chapter_id, locale="nl", **kw)
        db.add(roster)
        db.flush()
        logger.info("seed_roster_created", roster_id=roster.id, name=name)
        return roster

    def _chore(roster_id: str, ordinal: int, name: str, slots: list[int], emoji: str) -> Chore:
        c = Chore(roster_id=roster_id, name=name, ordinal=ordinal, cycle_slots=slots, emoji=emoji)
        db.add(c)
        db.flush()
        return c

    def _vol(
        roster_id: str,
        name: str,
        chore_ids: list[str],
        *,
        email: str | None = None,
        away: tuple[date, date] | None = None,
    ) -> Volunteer:
        _, token_hash = edit_token.new_edit_token()
        v = Volunteer(
            roster_id=roster_id,
            display_name=name,
            edit_token_hash=token_hash,
            email_reminders=email is not None,
            encrypted_email=encryption.encrypt(email) if email else None,
        )
        db.add(v)
        db.flush()
        for cid in chore_ids:
            db.add(Enrollment(volunteer_id=v.id, chore_id=cid))
        if away is not None:
            db.add(VolunteerAvailability(volunteer_id=v.id, start_date=away[0], end_date=away[1]))
        return v

    def _shift(chore_id: str, on: date, vol: Volunteer | None, status: str, *, done: bool = False) -> Shift:
        s = Shift(
            chore_id=chore_id,
            on_date=on,
            slot_index=0,
            volunteer_id=vol.id if vol else None,
            status=status,
            done_at=now if done else None,
        )
        db.add(s)
        db.flush()
        return s

    def _ev(roster_id: str, vol: Volunteer, kind: str, shift_id: str | None = None) -> None:
        db.add(ShiftEvent(roster_id=roster_id, volunteer_id=vol.id, kind=kind, shift_id=shift_id))

    # --- A. forming (draft, not yet started) -------------------------
    forming = _roster(
        "Weekmarkt-kraam",
        description_nl="Elke zaterdag een kraam op de markt. We zoeken nog mensen!",
        starts_on=wd(5, 1),  # next Saturday
        period_weeks=1,
        commit_horizon_days=21,
        reminder_enabled=True,
        reminder_days_before=1,
        activated_at=None,  # forming
    )
    if forming is not None:
        opbouw = _chore(forming.id, 1, "Opbouwen", [5], "📦")  # Sat
        afbreken = _chore(forming.id, 2, "Afbreken", [5], "🧹")
        _vol(forming.id, "Joris", [opbouw.id])
        _vol(forming.id, "Fatima", [opbouw.id, afbreken.id])

    # --- B. running (active weekly café, mid-flight) -----------------
    running = _roster(
        "Sociaal café",
        description_nl="Wekelijks buurtcafé op vrijdag; schoonmaak op zaterdag.",
        location="Buurthuis Oost",
        starts_on=wd(4, -12),  # Friday, twelve weeks ago
        period_weeks=1,
        commit_horizon_days=21,
        reminder_enabled=True,
        reminder_days_before=1,
        activated_at=now - timedelta(days=84),
    )
    if running is not None:
        bar = _chore(running.id, 1, "Bar", [4], "🍻")  # Fri
        keuken = _chore(running.id, 2, "Keuken", [4], "🍲")  # Fri
        schoon = _chore(running.id, 3, "Schoonmaak", [5], "🧽")  # Sat
        weekday = {bar.id: 4, keuken.id: 4, schoon.id: 5}

        # Eight volunteers with uneven enrolment + an activity weight, so the
        # per-chore accountability bars vary a lot: Els carries three chores,
        # Fen barely shows up. (name, chores, weight, email, away)
        specs: list[tuple[str, list[Chore], int, str | None, tuple[date, date] | None]] = [
            ("Ada", [bar, keuken], 5, "ada@local.dev", None),
            ("Ben", [schoon], 4, None, None),
            ("Cas", [bar, schoon], 3, None, None),
            ("Do", [keuken], 2, None, (wd(4, 1), wd(6, 1))),  # away next weekend
            ("Els", [bar, keuken, schoon], 6, None, None),
            ("Fen", [schoon], 1, None, None),
            ("Gijs", [bar], 2, None, None),
            ("Hana", [keuken, schoon], 3, None, None),
        ]
        vols = {
            name: _vol(running.id, name, [c.id for c in chores], email=email, away=away)
            for name, chores, _weight, email, away in specs
        }

        def _pool(chore: Chore) -> list[str]:
            """Weighted assignment pool: each enrolled volunteer repeated by
            their activity weight, so busier people draw more occurrences."""
            return [name for name, chores, weight, *_ in specs if chore in chores for _ in range(weight)]

        # Twelve weeks of history: each weekly occurrence goes to a weighted
        # rotation of the enrolled pool; most get completed, some missed, some
        # handed off (assignee defers, next in the pool covers + completes).
        for wk in range(-12, 0):
            for ci, chore in enumerate((bar, keuken, schoon)):
                pool = _pool(chore)
                idx = (wk + 12) % len(pool)
                assignee = vols[pool[idx]]
                on = wd(weekday[chore.id], wk)
                n = (wk + 12) * 3 + ci
                if n % 11 == 5:
                    s = _shift(chore.id, on, assignee, "missed")
                    _ev(running.id, assignee, "assigned", s.id)
                    _ev(running.id, assignee, "missed", s.id)
                elif n % 7 == 3:
                    picker = vols[pool[(idx + 1) % len(pool)]]
                    s = _shift(chore.id, on, picker, "done", done=True)
                    _ev(running.id, assignee, "assigned", s.id)
                    _ev(running.id, assignee, "deferred", s.id)
                    _ev(running.id, picker, "covered", s.id)
                    _ev(running.id, picker, "completed", s.id)
                else:
                    s = _shift(chore.id, on, assignee, "done", done=True)
                    _ev(running.id, assignee, "assigned", s.id)
                    _ev(running.id, assignee, "completed", s.id)

        # Pin the real commit window from the projection (as the daily tick
        # does in production), so the calendar shows a fully-scheduled ~3
        # weeks rather than a couple of hand-placed shifts. Commits.
        db.flush()
        chore_tick.pin_roster(db, running, today)
        # Leave one upcoming shift up for grabs, so the calendar shows an
        # open cell too.
        up_for_grabs = (
            db.query(Shift)
            .join(Chore, Chore.id == Shift.chore_id)
            .filter(
                Chore.roster_id == running.id,
                Chore.name == "Keuken",
                Shift.on_date > today,
                Shift.status == "scheduled",
            )
            .order_by(Shift.on_date)
            .first()
        )
        if up_for_grabs is not None:
            up_for_grabs.volunteer_id = None
            up_for_grabs.status = "open"

        # A latecomer who enrolled *after* the window was pinned: still
        # "pending" (not in the confirmed window), so the details page shows
        # the "fold in now" button and its preview has something to fold in.
        _vol(running.id, "Nova", [bar.id, schoon.id])

    # --- C. archived (finished campaign) -----------------------------
    archived = _roster(
        "Kerstpakkettenactie",
        description_nl="Pakketten inpakken en rondbrengen — actie afgerond.",
        starts_on=today - timedelta(days=42),
        ends_on=today - timedelta(days=7),
        period_weeks=1,
        commit_horizon_days=14,
        reminder_enabled=False,
        reminder_days_before=1,
        activated_at=now - timedelta(days=42),
        archived_at=now - timedelta(days=3),
    )
    if archived is not None:
        inpak = _chore(archived.id, 1, "Inpakken", [5], "🎁")  # Sat
        bezorg = _chore(archived.id, 2, "Bezorgen", [6], "🚲")  # Sun
        gwen = _vol(archived.id, "Gwen", [inpak.id, bezorg.id])
        hugo = _vol(archived.id, "Hugo", [inpak.id])
        iris = _vol(archived.id, "Iris", [bezorg.id])
        for week, packer in ((-5, gwen), (-4, hugo), (-3, gwen)):
            s = _shift(inpak.id, wd(5, week), packer, "done", done=True)
            _ev(archived.id, packer, "assigned", s.id)
            _ev(archived.id, packer, "completed", s.id)
        deliver = _shift(bezorg.id, wd(6, -3), iris, "done", done=True)
        _ev(archived.id, iris, "assigned", deliver.id)
        _ev(archived.id, iris, "completed", deliver.id)
        skipped = _shift(bezorg.id, wd(6, -4), iris, "missed")
        _ev(archived.id, iris, "assigned", skipped.id)
        _ev(archived.id, iris, "missed", skipped.id)


def _seed_forms(db: Session, *, created_by: str, chapter_id: str | None, now: datetime) -> None:
    """Three demo questionnaires: one with a full set of responses, one
    fresh (no submissions yet), and one archived. Idempotent (keyed on
    ``(name, created_by)``)."""

    def _form(name: str, description: str, *, archived_at: datetime | None = None) -> Form | None:
        if db.query(Form).filter(Form.name_nl == name, Form.created_by == created_by).first():
            return None
        f = Form(
            slug=new_slug(),
            name_nl=name,
            description_nl=description,
            created_by=created_by,
            chapter_id=chapter_id,
            locale="nl",
            archived_at=archived_at,
        )
        db.add(f)
        db.flush()
        logger.info("seed_form_created", form_id=f.id, name=name)
        return f

    def _q(
        form_id: str,
        ordinal: int,
        kind: str,
        prompt: str,
        *,
        required: bool = True,
        options: list[str] | None = None,
        low: str | None = None,
        high: str | None = None,
    ) -> FormQuestion:
        q = FormQuestion(
            form_id=form_id,
            ordinal=ordinal,
            kind=kind,
            prompt=prompt,
            required=required,
            options=options or [],
            low_label=low,
            high_label=high,
        )
        db.add(q)
        db.flush()
        return q

    def _submit(form_id: str, questions: list[FormQuestion], display_name: str | None, answers: list[object]) -> None:
        _, token_hash = edit_token.new_edit_token()
        sub = FormSubmission(form_id=form_id, display_name=display_name, edit_token_hash=token_hash)
        db.add(sub)
        db.flush()
        for q, ans in zip(questions, answers, strict=True):
            if ans is None:
                continue
            db.add(
                FormResponse(
                    form_id=form_id,
                    question_id=q.id,
                    submission_id=sub.id,
                    answer_int=ans if isinstance(ans, int) else None,
                    answer_text=ans if isinstance(ans, str) else None,
                    answer_choices=ans if isinstance(ans, list) else None,
                )
            )

    # --- A. active, with a spread of responses -----------------------
    survey = _form("Lidmaatschapsenquête", "Help ons de afdeling beter te maken — duurt twee minuten.")
    if survey is not None:
        qs = [
            _q(survey.id, 1, "rating", "Hoe tevreden ben je met de afdeling?", low="Ontevreden", high="Zeer tevreden"),
            _q(survey.id, 2, "single_choice", "Hoe vaak kom je langs?", options=["Wekelijks", "Maandelijks", "Zelden"]),
            _q(
                survey.id,
                3,
                "multi_choice",
                "Welke thema's spreken je aan?",
                options=["Wonen", "Klimaat", "Zorg", "Werk"],
            ),
            _q(survey.id, 4, "short_text", "Waar kunnen we mee helpen?", required=False),
            _q(survey.id, 5, "text", "Verdere opmerkingen", required=False),
        ]
        # single_choice carries a one-element list, same shape as multi_choice.
        _submit(survey.id, qs, "Nore", [5, ["Wekelijks"], ["Wonen", "Klimaat"], "Meer avondactiviteiten.", None])
        _submit(survey.id, qs, "Anoniem", [4, ["Maandelijks"], ["Zorg"], None, "Fijne mensen, ga zo door!"])
        _submit(survey.id, qs, "Teun", [3, ["Zelden"], ["Werk", "Wonen"], "Bijeenkomsten dichter bij het OV.", None])
        _submit(survey.id, qs, "Yara", [5, ["Wekelijks"], ["Klimaat", "Zorg", "Werk"], None, None])

    # --- B. active, no submissions yet -------------------------------
    signup = _form("Aanmelding werkgroep", "Sluit je aan bij een werkgroep. We nemen daarna contact op.")
    if signup is not None:
        _q(signup.id, 1, "single_choice", "Welke werkgroep?", options=["Wonen", "Klimaat", "Zorg"])
        _q(signup.id, 2, "text", "Waarom wil je meedoen?")

    # --- C. archived, with a few responses ---------------------------
    evaluation = _form(
        "Evaluatie zomerkamp",
        "Korte terugblik op het zomerkamp.",
        archived_at=now - timedelta(days=10),
    )
    if evaluation is not None:
        eqs = [
            _q(evaluation.id, 1, "rating", "Algemene beoordeling", low="Slecht", high="Top"),
            _q(evaluation.id, 2, "short_text", "Wat kan volgend jaar beter?", required=False),
        ]
        _submit(evaluation.id, eqs, "Kampganger", [5, "Meer schaduwplekken."])
        _submit(evaluation.id, eqs, "Bo", [4, None])
        _submit(evaluation.id, eqs, None, [3, "Eten was te weinig voor de vegetariërs."])


def _seed_datepolls(db: Session, *, created_by: str, chapter_id: str | None, now: datetime) -> None:
    """Three demo datepolls: one busy poll with responses, one fresh (no
    responses yet), and one archived. Idempotent (keyed on
    ``(name, created_by)``)."""
    today = now.date()

    def _poll(
        name: str,
        description: str,
        *,
        location: str | None = None,
        archived_at: datetime | None = None,
    ) -> Datepoll | None:
        if db.query(Datepoll).filter(Datepoll.name_nl == name, Datepoll.created_by == created_by).first():
            return None
        p = Datepoll(
            slug=new_slug(),
            name_nl=name,
            description_nl=description,
            location=location,
            created_by=created_by,
            chapter_id=chapter_id,
            locale="nl",
            archived_at=archived_at,
        )
        db.add(p)
        db.flush()
        logger.info("seed_datepoll_created", datepoll_id=p.id, name=name)
        return p

    def _slot(poll_id: str, on: date, start: time | None = None, end: time | None = None) -> DatepollSlot:
        s = DatepollSlot(datepoll_id=poll_id, on_date=on, start_time=start, end_time=end)
        db.add(s)
        db.flush()
        return s

    def _respond(
        poll_id: str,
        slots: list[DatepollSlot],
        display_name: str | None,
        note: str | None,
        avail: list[str | None],
    ) -> None:
        _, token_hash = edit_token.new_edit_token()
        sub = DatepollSubmission(datepoll_id=poll_id, display_name=display_name, note=note, edit_token_hash=token_hash)
        db.add(sub)
        db.flush()
        for slot, av in zip(slots, avail, strict=True):
            if av is None:
                continue
            db.add(DatepollResponse(submission_id=sub.id, datepoll_slot_id=slot.id, availability=av))

    # --- A. active, several respondents ------------------------------
    meeting = _poll(
        "Volgende ledenvergadering",
        "Prik een avond die voor de meesten werkt.",
        location="Buurthuis Centrum",
    )
    if meeting is not None:
        slots = [
            _slot(meeting.id, today + timedelta(days=7), time(19, 0), time(21, 0)),
            _slot(meeting.id, today + timedelta(days=9), time(19, 0), time(21, 0)),
            _slot(meeting.id, today + timedelta(days=14), time(20, 0), time(22, 0)),
        ]
        _respond(meeting.id, slots, "Nore", "Kan het liefst vroeg.", ["yes", "yes", "no"])
        _respond(meeting.id, slots, "Teun", None, ["yes", "maybe", "yes"])
        _respond(meeting.id, slots, "Yara", "Na 19:30 lukt beter.", ["no", "yes", "yes"])
        _respond(meeting.id, slots, "Anoniem", None, ["maybe", "yes", "maybe"])

    # --- B. active, no responses yet ---------------------------------
    outing = _poll("Teamuitje datumprikker", "Zoek een zaterdag voor het teamuitje.")
    if outing is not None:
        _slot(outing.id, today + timedelta(days=12))
        _slot(outing.id, today + timedelta(days=19))
        _slot(outing.id, today + timedelta(days=26))

    # --- C. archived, with responses ---------------------------------
    visit = _poll(
        "Locatiebezoek",
        "Datumprikker voor het locatiebezoek — inmiddels geweest.",
        archived_at=now - timedelta(days=5),
    )
    if visit is not None:
        vslots = [
            _slot(visit.id, today - timedelta(days=21)),
            _slot(visit.id, today - timedelta(days=18)),
        ]
        _respond(visit.id, vslots, "Bo", None, ["yes", "no"])
        _respond(visit.id, vslots, "Kai", "Ik reed.", ["yes", "yes"])
        _respond(visit.id, vslots, "Sam", None, ["maybe", "yes"])


def _seed_demo_responses(db: Session, occurrence_id: str) -> None:
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
                    occurrence_id=occurrence_id,
                    question_key=key,
                    submission_id=sub_id,
                    answer_int=value if isinstance(value, int) else None,
                    answer_text=value if isinstance(value, str) else None,
                )
            )
    logger.info("seed_demo_feedback", occurrence_id=occurrence_id, count=len(_DEMO_SUBMISSIONS))
