"""Background-worker entrypoint.

Runs the scheduled email sweeps (reminder + feedback) in a
process separate from the user-facing API. The API container
runs with ``DISABLE_SCHEDULER=1`` so its uvicorn workers don't
all fire the same sweep concurrently — that's how we'd send each
reminder four times on a four-worker deploy. This entrypoint
owns the sweeps; runs as a single replica.

Local:
    DISABLE_SCHEDULER=0 uv run python -m backend.worker

Container:
    same image as the API; override CMD to
    ``["uv", "run", "--no-dev", "python", "-m", "backend.worker"]``.
    Set ``DISABLE_SCHEDULER`` to anything *except* ``1`` (or unset
    it) so the scheduler is allowed to start in this process.
"""

import os
import signal
import threading

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal
from .migrate import run_migrations
from .services import email_lifecycle, feedback_worker, reminder_worker

logger = structlog.get_logger()


def main() -> None:
    # Migrations are idempotent. Running them here as well as in
    # the API container is safe — alembic skips already-applied
    # revisions — and means the worker can boot cleanly on its
    # own if we deploy it before the API.
    run_migrations()

    # Reap any signup left in ``pending`` with a message_id from a
    # prior crash mid-send. Those rows would otherwise be picked
    # up on the next sweep and double-send. Done before the
    # scheduler starts so the first tick sees a clean slate.
    db = SessionLocal()
    try:
        reaped = email_lifecycle.reap_partial_sends(db)
        if reaped:
            logger.info("worker_boot_reaped", count=reaped)
    finally:
        db.close()

    # Also catch up on any reminder rows whose 72h pre-event
    # window passed during a prior outage. APScheduler's
    # ``interval`` trigger doesn't fire at boot — only after the
    # first interval elapses — so without this initial call a
    # multi-hour gap would never get cleaned up if the worker
    # restarts more often than the daily reaper would run.
    # Wrapped because a transient DB hiccup at boot shouldn't
    # take the whole worker process down — log loud, continue,
    # the daily scheduled tick will retry.
    try:
        boot_reaped = reminder_worker.reap_expired()
        if boot_reaped:
            logger.info("worker_boot_reap_expired", count=boot_reaped)
    except Exception:
        logger.exception("worker_boot_reap_expired_failed")

    # BackgroundScheduler runs the sweeps in a worker thread, which
    # leaves the main thread free to block on a signal-aware
    # event. (BlockingScheduler.start() uses an internal
    # threading.Event whose wait() in CPython doesn't reliably
    # surface SIGTERM until the wakeup interval — could mean the
    # process ignores ``docker stop`` until the next hourly tick.)
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        feedback_worker.run_once, "interval", hours=1, id="feedback_sweep"
    )
    scheduler.add_job(
        reminder_worker.run_once, "interval", hours=1, id="reminder_sweep"
    )

    # Recovery sweeps. Both run in addition to the boot-time
    # ``reap_partial_sends`` call below so a long-running
    # container that never gets restarted still self-heals from
    # stuck rows.
    def _reap_partial() -> None:
        # Wrapper so APScheduler doesn't try to schedule a
        # closure-bound DB session. Each tick gets a fresh one.
        db = SessionLocal()
        try:
            email_lifecycle.reap_partial_sends(db)
        finally:
            db.close()

    scheduler.add_job(
        _reap_partial, "interval", hours=1, id="reap_partial_sends"
    )
    # Daily catch-up: reminders pending for events that have
    # already started (72h window passed without a successful
    # tick — typical cause: the worker was down across the
    # window). Flip those to not_applicable so the ciphertext
    # eventually gets wiped.
    scheduler.add_job(
        reminder_worker.reap_expired, "interval", hours=24, id="reminder_reap_expired"
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
    # The DISABLE_SCHEDULER guard is a defence in depth: if the
    # operator accidentally points the worker entrypoint at an
    # environment where DISABLE_SCHEDULER=1 is set (typical for
    # the API container), we crash loudly instead of silently
    # doing nothing.
    if os.environ.get("DISABLE_SCHEDULER") == "1":
        raise SystemExit(
            "DISABLE_SCHEDULER=1 is set but the worker entrypoint "
            "needs the scheduler enabled. Unset it on this container."
        )
    main()
