"""Cron entry-points + the ``migrate`` pre-launch hook.

Each subcommand does one sweep and exits. Coolify cron (or any
external scheduler) invokes them on the documented cadence:

    python -m backend.cli migrate                  # API container start
    python -m backend.cli dispatch reminder        # hourly
    python -m backend.cli dispatch feedback        # hourly
    python -m backend.cli reap-partial             # hourly (offset)
    python -m backend.cli reap-expired             # daily
    python -m backend.cli reap-auth-tokens         # daily

The ``migrate`` subcommand runs alembic to HEAD as a one-shot
before uvicorn forks its workers (Dockerfile CMD chains the two).
Running migrations from inside ``backend.main``'s import path
races when ``WEB_CONCURRENCY > 1``: every worker re-imports the
app module, and N workers concurrently issuing
``CREATE TABLE alembic_version`` collide on
``pg_type_typname_nsp_index`` and crash the supervisor.

Sweeps still call ``run_migrations()`` themselves — single-process,
so no race — which keeps a cron tick that lands before the API's
first deploy from running against a stale schema.

Sentry init mirrors ``main.py`` so an exception inside the sweep
reaches the alerting pipeline. Uncaught exceptions are re-raised
so the process exits non-zero, which Coolify surfaces as a failed
cron run; we don't want one tick's hiccup to silently mask a
real bug.
"""

import argparse
import sys
from typing import Any

import sentry_sdk
import structlog
from sentry_sdk.crons import capture_checkin

from .config import settings
from .database import SessionLocal
from .migrate import run_migrations
from .models import EmailChannel
from .services import admin_digest, mail_lifecycle

logger = structlog.get_logger()


def _init_sentry() -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            send_default_pii=False,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )


# Sentry Cron Monitor configs — schedule + margin + max_runtime per
# slug. Passed as ``monitor_config`` on the ``in_progress`` check-in
# so Sentry upserts the monitor on first run; no manual UI step.
# Schedules must match the Coolify cron schedules in
# ``docs/deploy.md`` § 6 — the deploy doc is the source of cadence,
# this dict mirrors it for Sentry's view of what "on time" means.
_CRON_MONITORS: dict[str, Any] = {
    "opkomst-cli-dispatch-reminder": {
        "schedule": {"type": "crontab", "value": "0 * * * *"},
        "checkin_margin": 5,
        "max_runtime": 30,
        "timezone": "UTC",
    },
    "opkomst-cli-dispatch-feedback": {
        "schedule": {"type": "crontab", "value": "0 * * * *"},
        "checkin_margin": 5,
        "max_runtime": 30,
        "timezone": "UTC",
    },
    "opkomst-cli-reap-partial": {
        "schedule": {"type": "crontab", "value": "30 * * * *"},
        "checkin_margin": 5,
        "max_runtime": 15,
        "timezone": "UTC",
    },
    "opkomst-cli-reap-expired": {
        "schedule": {"type": "crontab", "value": "0 3 * * *"},
        "checkin_margin": 30,
        "max_runtime": 30,
        "timezone": "UTC",
    },
    "opkomst-cli-reap-auth-tokens": {
        "schedule": {"type": "crontab", "value": "45 3 * * *"},
        "checkin_margin": 30,
        "max_runtime": 5,
        "timezone": "UTC",
    },
    "opkomst-cli-pending-digest": {
        "schedule": {"type": "crontab", "value": "0 9 * * 1"},
        "checkin_margin": 60,
        "max_runtime": 5,
        "timezone": "UTC",
    },
}


def _monitor_slug(args: argparse.Namespace) -> str | None:
    """Sentry monitor slug for a CLI invocation, or ``None`` for
    commands that are *not* scheduled crons (``migrate`` runs at
    every API container boot; ``seed-demo`` is local-mode only).
    For ``dispatch`` the channel becomes part of the slug —
    reminder and feedback are independent monitors with the same
    schedule but separate up-to-date signals."""
    if args.cmd == "dispatch":
        return f"opkomst-cli-dispatch-{args.channel}"
    if args.cmd in {
        "reap-partial",
        "reap-expired",
        "reap-auth-tokens",
        "pending-digest",
    }:
        return f"opkomst-cli-{args.cmd}"
    return None


def _dispatch(channel_name: str) -> int:
    try:
        channel = EmailChannel(channel_name)
    except ValueError as exc:
        raise SystemExit(f"unknown channel: {channel_name}") from exc
    n = mail_lifecycle.run_once(channel)
    logger.info("cli_dispatch_done", channel=channel_name, processed=n)
    return n


def _reap_partial() -> int:
    db = SessionLocal()
    try:
        return mail_lifecycle.reap_partial_sends(db)
    finally:
        db.close()


def _reap_expired() -> int:
    return mail_lifecycle.reap_expired()


def _reap_auth_tokens() -> int:
    """Delete expired single-use magic-link rows from both auth
    token tables. Each redeem path already 410s on
    expired-or-missing, so this sweep is hygiene only — keeps the
    tables from growing monotonically as users request links they
    never click. Returns the combined count for the cron log."""
    from datetime import UTC, datetime

    from .models import LoginToken, RegistrationToken

    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        login_n = db.query(LoginToken).filter(LoginToken.expires_at < now).delete()
        reg_n = db.query(RegistrationToken).filter(RegistrationToken.expires_at < now).delete()
        db.commit()
        logger.info("auth_tokens_reaped", login_tokens=login_n, registration_tokens=reg_n)
        return login_n + reg_n
    finally:
        db.close()


def _pending_digest() -> int:
    return admin_digest.send_pending_digest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_dispatch = sub.add_parser("dispatch", help="Run one channel sweep.")
    p_dispatch.add_argument("channel", choices=[c.value for c in EmailChannel])
    sub.add_parser("reap-partial", help="Reap stuck partial sends.")
    sub.add_parser(
        "reap-expired",
        help="Finalise pending dispatches whose channel window has long passed.",
    )
    sub.add_parser(
        "reap-auth-tokens",
        help="Delete expired login + registration magic-link tokens.",
    )
    sub.add_parser(
        "pending-digest",
        help="Email every admin a weekly digest of accounts awaiting approval.",
    )
    sub.add_parser(
        "migrate",
        help="Run alembic to HEAD. The API Dockerfile's CMD chains "
        "this before uvicorn so workers don't race on bootstrap.",
    )
    sub.add_parser(
        "seed-demo",
        help="Local-mode only: insert two demo accounts + an upcoming and a past event.",
    )

    args = parser.parse_args(argv)

    _init_sentry()
    run_migrations()

    # Sentry Cron Monitors: send a check-in at start + end so a
    # missed run pages someone before the email queue backs up.
    # The ``monitor_config`` on the in-progress check-in upserts
    # the monitor in Sentry — no manual UI step. Non-cron commands
    # (``migrate`` runs at every API boot, ``seed-demo`` is
    # local-mode only) skip check-ins entirely; ``capture_checkin``
    # against an unknown slug without ``monitor_config`` is what
    # produces the "monitor that does not exist" rejection.
    monitor_slug = _monitor_slug(args)
    check_in_id: str | None = None
    if monitor_slug is not None:
        check_in_id = capture_checkin(
            monitor_slug=monitor_slug,
            status="in_progress",
            monitor_config=_CRON_MONITORS[monitor_slug],
        )

    try:
        if args.cmd == "dispatch":
            _dispatch(args.channel)
        elif args.cmd == "reap-partial":
            _reap_partial()
        elif args.cmd == "reap-expired":
            _reap_expired()
        elif args.cmd == "reap-auth-tokens":
            _reap_auth_tokens()
        elif args.cmd == "pending-digest":
            _pending_digest()
        elif args.cmd == "migrate":
            # ``run_migrations()`` already ran above as part of the
            # cron preamble — this branch exists so the API
            # container's CMD can chain ``cli migrate && uvicorn``
            # explicitly. The body is intentionally empty: the work
            # already happened.
            logger.info("cli_migrate_done")
        elif args.cmd == "seed-demo":
            from .seed import run_local_demo

            run_local_demo()
        else:
            parser.error(f"unknown command: {args.cmd}")
    except Exception:
        # Capture-and-reraise: Coolify cron will surface the
        # non-zero exit, but the FastAPI / Starlette Sentry
        # integrations only catch HTTP-served exceptions, so
        # without this an uncaught error in a cron sweep would
        # log to stdout and never alert. Re-raise so the
        # process exits non-zero (Coolify retry policy still
        # applies).
        sentry_sdk.capture_exception()
        if monitor_slug is not None:
            capture_checkin(
                monitor_slug=monitor_slug,
                check_in_id=check_in_id,
                status="error",
            )
        raise

    if monitor_slug is not None:
        capture_checkin(
            monitor_slug=monitor_slug,
            check_in_id=check_in_id,
            status="ok",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
