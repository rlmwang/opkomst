"""Background-worker entrypoint.

Runs the scheduled email sweeps (reminder + feedback) in a
process separate from the user-facing API. The API binary
(``backend/main.py``) does NOT import APScheduler at all — that
removes the historical class of bug where every uvicorn replica
booted its own scheduler and fired each scheduled email N times.
``backend/worker.py`` is the only place the scheduler exists; run
it as a single replica.

Local:
    uv run python -m backend.worker

Container:
    same image as the API, override CMD to
    ``["uv", "run", "--no-dev", "python", "-m", "backend.worker"]``.
"""

import os
import signal
import threading

import sentry_sdk
import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal
from .migrate import run_migrations
from .services import email_dispatcher, email_reaper
from .services.email_channels import ALL_CHANNELS

logger = structlog.get_logger()


def _reap_partial() -> int:
    """Fresh DB session per call so APScheduler doesn't carry one
    across ticks."""
    db = SessionLocal()
    try:
        return email_reaper.reap_partial_sends(db)
    finally:
        db.close()


def _safe_reap(name: str, fn) -> None:  # noqa: ANN001
    """Run a reaper call, swallowing exceptions so one bad tick
    doesn't take the worker down. ``email_reaper`` itself logs
    success counts; this wrapper only surfaces failures."""
    try:
        fn()
    except Exception:
        logger.exception("reap_failed", name=name)

# Mirror the API container's Sentry setup so worker-thread
# exceptions (the email sweeps run in this process) actually
# reach Sentry. The FastAPI / Starlette integrations only catch
# HTTP-served exceptions; without an explicit init here, every
# send failure or scheduled-job crash would log to stdout but
# never alert.
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        send_default_pii=False,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
    )
    logger.info("sentry_initialized", process="worker")


def main() -> None:
    # Migrations are idempotent. Running them here as well as in
    # the API container is safe — alembic skips already-applied
    # revisions — and means the worker can boot cleanly on its
    # own if we deploy it before the API.
    run_migrations()

    # Boot-time reaper pass. ``email_reaper`` already logs its own
    # success counts; we wrap each call so a transient DB hiccup
    # can't take the worker down before the scheduler even starts.
    _safe_reap("partial_sends", _reap_partial)
    _safe_reap("expired_windows", email_reaper.reap_expired_windows)
    _safe_reap("post_event_emails", email_reaper.purge_post_event_emails)

    # BackgroundScheduler runs the sweeps in a worker thread,
    # which leaves the main thread free to block on a
    # signal-aware event. (BlockingScheduler.start() uses an
    # internal threading.Event whose wait() in CPython doesn't
    # reliably surface SIGTERM until the wakeup interval — that
    # would mean the process ignores ``docker stop`` until the
    # next hourly tick.)
    scheduler = BackgroundScheduler()
    # One sweep job per channel, parameterised over the same
    # generic dispatcher. Adding a third channel is a single
    # ``ChannelSpec`` constant in ``email_channels.py``; this
    # loop picks it up automatically.
    for spec in ALL_CHANNELS:
        scheduler.add_job(
            email_dispatcher.run_once,
            "interval",
            hours=1,
            id=f"{spec.channel.value}_sweep",
            args=(spec,),
        )

    scheduler.add_job(
        lambda: _safe_reap("partial_sends", _reap_partial),
        "interval",
        hours=1,
        id="reap_partial_sends",
    )
    # Daily catch-up: dispatches stuck pending after their
    # event already started.
    scheduler.add_job(
        lambda: _safe_reap("expired_windows", email_reaper.reap_expired_windows),
        "interval",
        hours=24,
        id="reap_expired_windows",
    )
    # Daily privacy backstop: ≥7 days post-event, wipe any leftover
    # ciphertext that other paths missed.
    scheduler.add_job(
        lambda: _safe_reap("post_event_emails", email_reaper.purge_post_event_emails),
        "interval",
        hours=24,
        id="purge_post_event_emails",
    )

    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: object) -> None:  # noqa: ARG001
        logger.info("worker_shutdown_requested", signal=signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler.start()
    logger.info("worker_started", interval_hours=1)

    # Block the main thread on a plain Event — interruptible by
    # SIGTERM/SIGINT via the handler above, no APScheduler-internal
    # locking in the way. ``wait()`` with no timeout polls
    # responsively for signals on every interpreter check
    # interval.
    stop_event.wait()

    # ``wait=True`` on shutdown blocks until any in-flight sweep
    # tick finishes its work, so SIGTERM mid-SMTP doesn't strand
    # a signup with ciphertext wiped but status still ``pending``.
    scheduler.shutdown(wait=True)
    logger.info("worker_stopped")


if __name__ == "__main__":
    main()
