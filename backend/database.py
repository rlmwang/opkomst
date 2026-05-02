from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.database_url,
    # Pool hygiene under Coolify's Docker bridge network, observed
    # via Server-Timing telemetry: idle pool connections were being
    # silently reaped by NAT, causing ``pool_pre_ping``'s SELECT 1
    # to hang on the OS TCP read timeout (~2 s per checkout) before
    # SQLAlchemy gave up and opened a fresh socket. Two parallel
    # GETs after an idle period would each pay the full ~2.5 s in
    # handler time, with the actual queries only milliseconds.
    #
    # The structural fix is TCP keepalives in ``connect_args``: the
    # kernel sends a probe every 30 s, which (a) keeps the NAT
    # entry alive so the socket isn't reaped in the first place,
    # and (b) on a peer that genuinely died, fails after 3 missed
    # probes (~30 s) instead of the default minutes-long TCP
    # timeout.
    #
    # ``pool_pre_ping`` stays as defence-in-depth for the rare
    # cleanly-closed case (PG restart). ``pool_recycle=1800`` (30
    # min) keeps connections alive long enough that user pauses
    # between actions don't force a fresh TCP handshake every
    # time — keepalives above keep the socket healthy through
    # NAT idle, and pre_ping handles the rare PG-side close. The
    # earlier 240 s recycle was paranoid: telemetry showed users
    # pausing 5–10 min between actions paid the new-connection
    # cost every single time. ``pool_size`` bumped to 10 (default
    # 5) so a four-parallel-GET dashboard load doesn't exhaust the
    # pool and serialize on checkout.
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def warmup() -> None:
    """Pre-warm a worker so the first real request doesn't pay
    one-shot cold-compile cost. Telemetry probe (commit 4d3fec7
    follow-up): a fake-slug ``/e/{slug}`` request landed at 6.7 s
    cold, 42 ms warm — same SQL/Pydantic/file-cache compilation
    cost we'd already seen on the by-slug API. Each worker
    independently pays this on first hit; warming them all on
    boot moves that cost out of the user's request path.

    What the warmup exercises:
    * SQLAlchemy SQL compilation for the slug-lookup query shape
      (``get_event_by_slug_any``), the signup-aggregate, and the
      chapter lookup — the three shapes the public sign-up page
      and dashboard use.
    * The OS file cache for ``public-event.html`` (one ``read_text``
      call) so the first real ``/e/{slug}`` doesn't have a cold
      page-cache miss.
    * Pydantic v2 first-use model compilation for ``EventOut``
      via a ``model_dump_json`` on a synthesized instance — the
      heaviest hidden cost on cold paths that serialize an event.

    Called once per worker from the FastAPI lifespan. Failures
    are swallowed: the warmup is best-effort, the app still
    starts if the DB happens to be unreachable at boot."""
    import pathlib

    from sqlalchemy import text

    from .models import Chapter, Signup
    from .schemas.events import EventOut
    from .services import events as events_svc

    try:
        db: Session = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            # Compile the slug-lookup query shape (the exact same
            # call ``_serve_public_event`` makes — this is the
            # one that was costing 4 s of handler time cold).
            events_svc.get_event_by_slug_any(db, "__warmup__")
            # Other query shapes used by the dashboard / details
            # page on first navigation after login.
            db.query(Signup.event_id).filter(Signup.event_id == "_warmup_").limit(0).all()
            db.query(Chapter.id, Chapter.name).filter(Chapter.id == "_warmup_").limit(0).all()
        finally:
            db.close()

        # Warm the OS file cache for ``public-event.html``. The
        # path mirrors the one ``backend.routers.spa`` resolves;
        # we don't import that module here to avoid a cycle.
        public_html = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "dist" / "public-event.html"
        if public_html.is_file():
            public_html.read_text(encoding="utf-8")

        # Warm Pydantic ``EventOut`` model_dump_json — the cold
        # first call compiles the serializer (50–500 ms on
        # Pydantic v2 for a non-trivial model).
        EventOut(
            id="00000000-0000-0000-0000-000000000000",
            slug="__warmup__",
            name="warmup",
            topic=None,
            location="warmup",
            latitude=None,
            longitude=None,
            starts_at="2026-01-01T00:00:00+00:00",  # type: ignore[arg-type]
            ends_at="2026-01-01T01:00:00+00:00",  # type: ignore[arg-type]
            source_options=[],
            help_options=[],
            feedback_enabled=False,
            reminder_enabled=False,
            locale="nl",
            chapter_id=None,
            chapter_name=None,
            attendee_count=0,
            archived=False,
        ).model_dump_json()
    except Exception:
        pass
