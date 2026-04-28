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

    # Both boot-time reapers are wrapped: a transient DB hiccup
    # shouldn't take the worker down. The hourly / daily
    # scheduled ticks retry on their own cadence.
    try:
        db = SessionLocal()
        try:
            reaped = email_reaper.reap_partial_sends(db)
            if reaped:
                logger.info("worker_boot_reap_partial", count=reaped)
        finally:
            db.close()
    except Exception:
        logger.exception("worker_boot_reap_partial_failed")

    try:
        boot_reaped = email_reaper.reap_expired_windows()
        if boot_reaped:
            logger.info("worker_boot_reap_expired", count=boot_reaped)
    except Exception:
        logger.exception("worker_boot_reap_expired_failed")

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

    def _reap_partial() -> None:
        # Wrapper so APScheduler doesn't try to schedule a
        # closure-bound DB session. Each tick gets a fresh one.
        db = SessionLocal()
        try:
            email_reaper.reap_partial_sends(db)
        finally:
            db.close()

    scheduler.add_job(
        _reap_partial, "interval", hours=1, id="reap_partial_sends"
    )
    # Daily catch-up: dispatches stuck pending after their
    # event already started.
    scheduler.add_job(
        email_reaper.reap_expired_windows,
        "interval",
        hours=24,
        id="reap_expired_windows",
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
