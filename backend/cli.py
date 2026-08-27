"""Cron entry-points + the ``migrate`` pre-launch hook.

Each subcommand does one sweep and exits. Coolify cron (or any
external scheduler) invokes them on the documented cadence:

    python -m backend.cli migrate                  # API container start
    python -m backend.cli dispatch reminder        # hourly
    python -m backend.cli dispatch feedback        # hourly
    python -m backend.cli reap-partial             # hourly (offset)
    python -m backend.cli reap-expired             # daily
    python -m backend.cli reap-auth-tokens         # daily
    python -m backend.cli reap-images              # daily

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
from .services import admin_digest, image_reaper, mail_lifecycle

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
    "opkomst-cli-dispatch-chore-reminder": {
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
    "opkomst-cli-reap-images": {
        # After the token sweep, and well clear of the ticks: it talks
        # to the image host, so it is the one sweep that can be slow.
        "schedule": {"type": "crontab", "value": "15 4 * * *"},
        "checkin_margin": 30,
        "max_runtime": 30,
        "timezone": "UTC",
    },
    "opkomst-cli-pending-digest": {
        "schedule": {"type": "crontab", "value": "0 9 * * 1"},
        "checkin_margin": 60,
        "max_runtime": 5,
        "timezone": "UTC",
    },
    "opkomst-cli-roster-tick": {
        "schedule": {"type": "crontab", "value": "0 2 * * *"},
        "checkin_margin": 30,
        "max_runtime": 30,
        "timezone": "UTC",
    },
    "opkomst-cli-event-tick": {
        "schedule": {"type": "crontab", "value": "0 2 * * *"},
        "checkin_margin": 30,
        "max_runtime": 30,
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
        "reap-images",
        "pending-digest",
        "roster-tick",
        "event-tick",
    }:
        return f"opkomst-cli-{args.cmd}"
    return None


def _dispatch(channel_name: str) -> int:
    if channel_name == "chore-reminder":
        n = mail_lifecycle.run_chore_reminders()
        logger.info("cli_dispatch_done", channel=channel_name, processed=n)
        return n
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


def _sync_tenants() -> None:
    """Reconcile the organisations to ``TENANTS``. Runs in the same
    preamble as the migrations, so every deploy and every cron
    invocation leaves the table matching the environment — the env var
    is the source of truth, and nobody has to remember a command."""
    from .services import tenants as tenants_svc

    db = SessionLocal()
    try:
        tenants_svc.sync_from_env(db)
    finally:
        db.close()


def _pending_digest() -> int:
    return admin_digest.send_pending_digest()


def _roster_tick() -> int:
    """Materialise + fairly assign chore shifts on the rolling horizon,
    and flip past-due scheduled shifts to missed. Returns the number of
    shifts created (for the cron log)."""
    from .services import chore_tick
    from .services.events import now_wallclock

    db = SessionLocal()
    try:
        rosters, shifts = chore_tick.run_tick(db, now_wallclock().date())
        logger.info("cli_roster_tick", rosters=rosters, shifts=shifts)
        return shifts
    finally:
        db.close()


def _tenant_plan(email: str, plan: str) -> int:
    """Move one account between ``free`` and ``paid``
    (``docs/design-paywall.md``). Platform-level, like the tenant list
    and the brand folders, so it is a command and not a page.

    Dropping to ``free`` is not just a flag: an account that may not
    mail its participants may not have the toggles on either, so this
    switches them off and deletes the pending dispatch rows behind them,
    the same cleanup an organiser's own toggle-off does. Without that a
    downgraded account keeps ciphertext on file for mail that will never
    be sent.

    Personal accounts only, found by the address they were created with:
    an organisation is paid because an operator put it in ``TENANTS``,
    and the boot reconcile holds it there."""
    from .database import SessionLocal
    from .models import EmailChannel, Event, Roster, Tenant
    from .services import mail_lifecycle, tenancy

    db = SessionLocal()
    try:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.deleted_at.is_(None), (Tenant.name == email) | (Tenant.slug == email))
            .first()
        )
        if tenant is None:
            print(f"No live account for {email!r}.")
            return 1
        if not tenant.is_personal:
            print(
                f"{tenant.name} is an organisation, and an organisation is paid because it is in TENANTS. "
                "Take the slug out of TENANTS to retire it; there is nothing to set here."
            )
            return 1
        # Spelled out rather than assigned through: the column is two
        # literals, and argparse hands over a plain string.
        tenant.plan = "paid" if plan == "paid" else "free"
        if plan == "free":
            # The rows carry ``tenant_id``, so the write guard wants the
            # account bound the same way a request would bind it.
            with tenancy.use(tenant.id, tenant.brand_slug):
                for event in db.query(Event).filter(Event.tenant_id == tenant.id).all():
                    channels: set[EmailChannel] = set()
                    if event.reminder_enabled:
                        channels.add(EmailChannel.REMINDER)
                        event.reminder_enabled = False
                    if event.feedback_enabled:
                        channels.add(EmailChannel.FEEDBACK)
                        event.feedback_enabled = False
                    mail_lifecycle.retire_event_channels(db, event_id=event.id, channels=channels)
                db.query(Roster).filter(Roster.tenant_id == tenant.id).update(
                    {Roster.reminder_enabled: False}, synchronize_session=False
                )
                db.flush()
        db.commit()
        logger.info("cli_tenant_plan", tenant_id=tenant.id, plan=plan)
        print(f"{tenant.name} is now {plan}.")
        return 0
    finally:
        db.close()


def _traffic_report(days: int) -> None:
    """Print what each surface did, per day totals collapsed.

    A report rather than a page. Traffic is platform-level, and this
    project keeps platform-level things out of the app on purpose: the
    tenant list is an env var, the brands are folders, and neither has
    a UI. A dashboard route would be the first exception and would need
    an auth surface built for it alone.

    Every number here is an aggregate that was never personal. See
    ``models/traffic.py`` for what is deliberately not counted."""
    from datetime import date, timedelta

    from sqlalchemy import func, select

    from .database import SessionLocal
    from .models.traffic import SURFACES, TrafficCount

    since = date.today() - timedelta(days=days)
    with SessionLocal() as session:
        rows = session.execute(
            select(TrafficCount.surface, TrafficCount.action, func.sum(TrafficCount.count))
            .where(TrafficCount.day >= since)
            .group_by(TrafficCount.surface, TrafficCount.action)
        ).all()

    totals: dict[str, dict[str, int]] = {}
    for surface, action, count in rows:
        totals.setdefault(surface, {})[action] = int(count or 0)

    print(f"\nTraffic, last {days} days (since {since})\n")
    print(f"  {'surface':<18}{'views':>9}{'submits':>10}{'rate':>8}")
    print(f"  {'-' * 43}")
    for surface in SURFACES:
        seen = totals.get(surface)
        if not seen:
            continue
        views, submits = seen.get("view", 0), seen.get("submit", 0)
        # A rate only means something where both are counted: the
        # create pages have no submit event, so they get no ratio
        # rather than a misleading 0%.
        rate = f"{submits / views:.0%}" if views and submits else ""
        print(f"  {surface:<18}{views:>9}{submits:>10}{rate:>8}")
    if not totals:
        print("  (nothing recorded yet)")
    print()


def _event_tick() -> int:
    """Materialise the incoming horizon edge of concrete occurrences for
    every live event. Returns the number of occurrences created (for the
    cron log)."""
    from .services import event_recurrence
    from .services.events import now_wallclock

    db = SessionLocal()
    try:
        events, occurrences = event_recurrence.run_tick(db, now_wallclock())
        logger.info("cli_event_tick", events=events, occurrences=occurrences)
        return occurrences
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_dispatch = sub.add_parser("dispatch", help="Run one channel sweep.")
    # ``chore-reminder`` rides the ``dispatch`` verb for operator muscle
    # memory, but it's not an EmailChannel (chores have no EmailDispatch
    # rows) — it routes to ``run_chore_reminders`` below.
    p_dispatch.add_argument("channel", choices=[c.value for c in EmailChannel] + ["chore-reminder"])
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
        "reap-images",
        help="Delete the images of entities archived longer than the grace period.",
    )
    sub.add_parser(
        "pending-digest",
        help="Email every admin a weekly digest of accounts awaiting approval.",
    )
    sub.add_parser(
        "roster-tick",
        help="Generate + fairly assign chore shifts on the rolling horizon.",
    )
    sub.add_parser(
        "event-tick",
        help="Materialise concrete event occurrences on the rolling horizon.",
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
    p_plan = sub.add_parser(
        "tenant-plan",
        help="Move one personal account between free and paid, by the address it was created with.",
    )
    p_plan.add_argument("tenant", help="The address a personal account was created with.")
    p_plan.add_argument("plan", choices=["free", "paid"])
    p_traffic = sub.add_parser(
        "traffic-report",
        help="Print page views and submissions per surface. There is no dashboard "
        "page on purpose: this is platform-level, like the tenant list and the "
        "brand folders, and those have no UI either.",
    )
    p_traffic.add_argument("--days", type=int, default=30, help="How far back to report. Default 30.")

    args = parser.parse_args(argv)

    _init_sentry()
    run_migrations()
    # Schema first, then the organisations the environment says exist.
    # Every invocation reconciles, so a deploy that adds a tenant to
    # ``TENANTS`` has it live the moment the container starts.
    _sync_tenants()

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
        elif args.cmd == "reap-images":
            image_reaper.reap_images()
        elif args.cmd == "pending-digest":
            _pending_digest()
        elif args.cmd == "roster-tick":
            _roster_tick()
        elif args.cmd == "event-tick":
            _event_tick()
        elif args.cmd == "migrate":
            # ``run_migrations()`` already ran above as part of the
            # cron preamble — this branch exists so the API
            # container's CMD can chain ``cli migrate && uvicorn``
            # explicitly. The body is intentionally empty: the work
            # already happened.
            logger.info("cli_migrate_done")
        elif args.cmd == "tenant-plan":
            return _tenant_plan(args.tenant, args.plan)
        elif args.cmd == "traffic-report":
            _traffic_report(args.days)
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
