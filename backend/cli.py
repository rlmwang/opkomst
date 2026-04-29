"""Cron entry-points.

Each subcommand does one sweep and exits. Coolify cron (or any
external scheduler) invokes them on the documented cadence:

    python -m backend.cli dispatch reminder        # hourly
    python -m backend.cli dispatch feedback        # hourly
    python -m backend.cli reap-partial             # hourly (offset)
    python -m backend.cli reap-expired             # daily
    python -m backend.cli reap-post-event-emails   # daily
    python -m backend.cli reap-login-tokens        # daily

Migrations are idempotent — alembic skips already-applied
revisions — and run on every invocation so a sweep that lands
before the API replica's first deploy still has a current schema.

Sentry init mirrors ``main.py`` so an exception inside the sweep
reaches the alerting pipeline. Uncaught exceptions are re-raised
so the process exits non-zero, which Coolify surfaces as a failed
cron run; we don't want one tick's hiccup to silently mask a
real bug.
"""

import argparse
import sys

import sentry_sdk
import structlog
from sentry_sdk.crons import capture_checkin

from .config import settings
from .database import SessionLocal
from .migrate import run_migrations
from .services import email_dispatcher, email_reaper
from .services.email_channels import EmailChannel, spec_for

logger = structlog.get_logger()


def _init_sentry() -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            send_default_pii=False,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )


def _dispatch(channel_name: str) -> int:
    try:
        channel = EmailChannel(channel_name)
    except ValueError as exc:
        raise SystemExit(f"unknown channel: {channel_name}") from exc
    spec = spec_for(channel)
    n = email_dispatcher.run_once(spec)
    logger.info("cli_dispatch_done", channel=channel_name, processed=n)
    return n


def _reap_partial() -> int:
    db = SessionLocal()
    try:
        return email_reaper.reap_partial_sends(db)
    finally:
        db.close()


def _reap_expired() -> int:
    return email_reaper.reap_expired_windows()


def _reap_post_event() -> int:
    return email_reaper.purge_post_event_emails()


def _reap_login_tokens() -> int:
    """Delete expired single-use magic-link rows. The redeem path
    already 410s on expired-or-missing, so this sweep is hygiene
    only — keeps the table from growing monotonically as users
    request links they never click."""
    from datetime import UTC, datetime

    from .models import LoginToken

    db = SessionLocal()
    try:
        n = db.query(LoginToken).filter(LoginToken.expires_at < datetime.now(UTC)).delete()
        db.commit()
        logger.info("login_tokens_reaped", deleted=n)
        return n
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_dispatch = sub.add_parser("dispatch", help="Run one channel sweep.")
    p_dispatch.add_argument("channel", choices=[c.value for c in EmailChannel])
    sub.add_parser("reap-partial", help="Reap stuck partial sends.")
    sub.add_parser("reap-expired", help="Reap reminders past their window.")
    sub.add_parser("reap-post-event-emails", help="≥7d post-event ciphertext purge.")
    sub.add_parser("reap-login-tokens", help="Delete expired magic-link tokens.")

    args = parser.parse_args(argv)

    _init_sentry()
    run_migrations()

    # Sentry Cron Monitors: send a check-in at start + end. If
    # Sentry hasn't heard from a job within the configured SLA
    # (set in the Sentry UI, per monitor slug) it raises an
    # incident — which is how you find out the cron host died
    # without waiting for the email queue to back up. Slug names
    # match the subcommand; configure each one in the Sentry UI.
    monitor_slug = f"opkomst-cli-{args.cmd}"
    check_in_id = capture_checkin(
        monitor_slug=monitor_slug,
        status="in_progress",
    )

    try:
        if args.cmd == "dispatch":
            _dispatch(args.channel)
        elif args.cmd == "reap-partial":
            _reap_partial()
        elif args.cmd == "reap-expired":
            _reap_expired()
        elif args.cmd == "reap-post-event-emails":
            _reap_post_event()
        elif args.cmd == "reap-login-tokens":
            _reap_login_tokens()
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
        capture_checkin(
            monitor_slug=monitor_slug,
            check_in_id=check_in_id,
            status="error",
        )
        raise

    capture_checkin(
        monitor_slug=monitor_slug,
        check_in_id=check_in_id,
        status="ok",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
