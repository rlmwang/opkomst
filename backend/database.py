from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings
from .services import tenancy as _tenancy

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
    # NAT idle, and pre_ping handles the rare PG-side close.
    #
    # ``pool_size=5, max_overflow=5`` gives each worker up to 10
    # concurrent PG connections. The pool is the app's real concurrency
    # ceiling: a request that needs a connection and cannot have one
    # waits here, not on Postgres, and it waits invisibly — the box
    # looks idle while people look at a spinner.
    #
    # It was 2 + 3, sized for one worker on a 512 MB VPS where every
    # idle slot cost a ~10 MB backend process. The host has 3.9 GB and
    # runs three workers, so the ceiling was 5 concurrent
    # database-touching requests per worker for no good reason.
    #
    # 3 workers × 10 = 30 connections, plus one per cron sweep, against
    # ``max_connections=60`` (``docs/deploy.md`` sizes the two together).
    # Raising either one alone is how a deploy runs out of connections.
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Authorisation is enforced in the routers and in ``services/access.py``;
# this is the layer under them. Every flush is checked against the
# tenant bound to the request, so a row of another organisation that
# somehow got loaded still cannot be written back. See
# ``services/tenancy.py``.
_tenancy.install_write_guard(Session)


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
            events_svc.get_occurrence_by_slug_any(db, "__warmup__")
            # Other query shapes used by the dashboard / details
            # page on first navigation after login.
            db.query(Signup.occurrence_id).filter(Signup.occurrence_id == "_warmup_").limit(0).all()
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
            name_nl="warmup",
            name_en=None,
            topic_nl=None,
            topic_en=None,
            location="warmup",
            latitude=None,
            longitude=None,
            starts_on="2026-01-01",  # type: ignore[arg-type]
            start_time="18:00:00",  # type: ignore[arg-type]
            end_time="20:00:00",  # type: ignore[arg-type]
            period_weeks=1,
            cycle_slots=[],
            span_weeks=None,
            horizon_days=90,
            source_options=[],
            help_options=[],
            feedback_enabled=False,
            reminder_enabled=False,
            listed=True,
            locale="nl",
            chapter_id=None,
            chapter_name=None,
            image_url=None,
            image_artist_instagram=None,
            next_starts_at=None,
            next_slug="__warmup__",
            attendee_count=0,
            archived=False,
        ).model_dump_json()
    except Exception:  # noqa: S110 — warm-up only; a failure here must not touch boot
        pass
