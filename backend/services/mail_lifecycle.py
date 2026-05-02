"""Email channel lifecycle: dispatch + reaper sweeps.

Two channels — REMINDER (fires ≤72h before an event) and FEEDBACK
(fires ≥24h after an event ends) — share one
``run_once(channel)`` function. Per-channel behaviour lives in
the ``CHANNELS`` table: each channel pins a template, a toggle
column on ``Event``, a window predicate, and a context builder.
``_process_one`` reads the row out of that table and mints a
FeedbackToken when the channel is FEEDBACK — the only branch
that survived the table-ification.

Adding a third channel: extend ``EmailChannel``, add an entry
to ``CHANNELS`` (template, toggle column, window predicate,
context builder), and ship the template file. Done.

Lifecycle of one row::

    [absent]                                 # no dispatch yet
       |
       | (signup creates the row at status=pending,
       |  encrypted_email set)
       v
    [pending, encrypted_email]
       |
       | (worker pre-mints message_id + commits — atomic claim)
       v
    [pending, message_id set, encrypted_email]   # crash here ⇒
                                                # reaper flips to failed
       |
       | (SMTP success / failure-after-retry)
       v
    [sent | failed, encrypted_email NULL]   # terminal

Privacy contract by lifecycle: a dispatch row carries the
encrypted address it'll send to; the same UPDATE that finalises
the row (sent / failed) nulls ``encrypted_email``; the reapers
that DELETE rows take the address with them. No cross-table
existence check, no separate wipe pass.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import EmailChannel, EmailDispatch, EmailStatus, Event, FeedbackToken
from . import encryption
from .mail import build_url, email_batch_size, emit_metric, new_message_id, send_with_retry

logger = structlog.get_logger()


# --- Channel constants --------------------------------------------

# How long a feedback link in an email stays redeemable.
FEEDBACK_TOKEN_TTL = timedelta(days=30)
# Reminders fire when the event is within this window of starting.
REMINDER_WINDOW = timedelta(hours=72)
# Feedback fires this long after an event ended.
FEEDBACK_DELAY = timedelta(hours=24)
# How long after an event ends before we force-wipe any remaining
# ciphertext for its signups. Comfortably past every other path.
POST_EVENT_PURGE_DELAY = timedelta(days=7)


# --- Window predicates --------------------------------------------


def _reminder_window(now: datetime) -> Any:
    """Reminder fires while ``now < event.starts_at <= now+72h``."""
    return (Event.starts_at > now) & (Event.starts_at <= now + REMINDER_WINDOW)


def _feedback_window(now: datetime) -> Any:
    """Feedback fires when the event ended ≥24h ago."""
    return Event.ends_at <= now - FEEDBACK_DELAY


# --- Context builders ---------------------------------------------

_DAY_NAMES = {
    "nl": ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
_MONTH_NAMES = {
    "nl": [
        "januari",
        "februari",
        "maart",
        "april",
        "mei",
        "juni",
        "juli",
        "augustus",
        "september",
        "oktober",
        "november",
        "december",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
}


def _format_date(when: datetime, locale: str) -> str:
    """Locale-aware long-form date: ``dinsdag 30 april 2026`` /
    ``Tuesday 30 April 2026``. Reminder emails fire ≤72h before
    the event, so the year is rare-but-useful (events spanning
    new year)."""
    days = _DAY_NAMES[locale]
    months = _MONTH_NAMES[locale]
    return f"{days[when.weekday()]} {when.day} {months[when.month - 1]} {when.year}"


def _format_time_range(starts_at: datetime, ends_at: datetime) -> str:
    """24-hour HH:MM–HH:MM. Same format in both locales."""
    return f"{starts_at:%H:%M}–{ends_at:%H:%M}"


def _osm_url(event: Event) -> str:
    """Pin-on-map URL when we have coordinates; fall back to a
    text search by ``location`` so the link still goes somewhere
    useful for events imported without geocoding."""
    if event.latitude is not None and event.longitude is not None:
        return (
            f"https://www.openstreetmap.org/?mlat={event.latitude}"
            f"&mlon={event.longitude}#map=17/{event.latitude}/{event.longitude}"
        )
    return f"https://www.openstreetmap.org/search?query={quote(event.location)}"


def build_reminder_context(event: Event) -> dict[str, Any]:
    """Public so events.py's per-event preview can render without
    touching a real send path."""
    return {
        "event_name": event.name,
        "event_url": build_url(f"e/{event.slug}"),
        "topic": event.topic,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "event_date": _format_date(event.starts_at, event.locale),
        "event_time": _format_time_range(event.starts_at, event.ends_at),
        "location": event.location,
        "map_url": _osm_url(event),
    }


def build_feedback_context(event: Event) -> dict[str, Any]:
    """For the live worker the URL is appended in
    ``_process_one`` once the per-signup token is minted. The
    preview path passes a synthetic token in directly."""
    return {"event_name": event.name}


# --- Channel definition table -------------------------------------


@dataclass(frozen=True, slots=True)
class _ChannelDef:
    """Per-channel knobs the worker, reapers and previewers all
    read. Adding a new channel is one entry in ``CHANNELS`` plus
    a template file and a context builder — no parallel if-trees
    spread across half a dozen helpers."""

    template: str
    toggle: Any  # SQLAlchemy column on Event
    window: Callable[[datetime], Any]  # SQL predicate factory
    context: Callable[[Event], dict[str, Any]]


CHANNELS: dict[EmailChannel, _ChannelDef] = {
    EmailChannel.REMINDER: _ChannelDef(
        template="reminder.html",
        toggle=Event.reminder_enabled,
        window=_reminder_window,
        context=build_reminder_context,
    ),
    EmailChannel.FEEDBACK: _ChannelDef(
        template="feedback.html",
        toggle=Event.feedback_enabled,
        window=_feedback_window,
        context=build_feedback_context,
    ),
}


def channel_enabled_for(channel: EmailChannel, event: Event) -> bool:
    """Read the per-event toggle column for ``channel`` against
    ``event``. The toggle column lives on the ``CHANNELS`` table
    as a SQLAlchemy ``InstrumentedAttribute``; pull its Python
    name and read it off the event instance."""
    return bool(getattr(event, CHANNELS[channel].toggle.key))


# --- Core dispatcher ----------------------------------------------


def _drop_feedback_token(db: Session, token: str | None) -> None:
    """Delete a previously-minted FeedbackToken so it doesn't sit
    redeemable for 30d after a failed send. No-op when the dispatch
    isn't FEEDBACK (token is None)."""
    if token is None:
        return
    db.query(FeedbackToken).filter(FeedbackToken.token == token).delete()


def _process_one(
    db: Session,
    channel: EmailChannel,
    event: Event,
    dispatch_id: str,
    ciphertext: bytes,
) -> None:
    """One dispatch through its lifecycle: atomic-claim,
    decrypt-or-fail, send, finalise.

    Takes primitives — ``dispatch_id`` (the dispatch row's PK)
    and ``ciphertext`` (its ``encrypted_email`` value) — instead
    of an ORM row. SQLAlchemy expires session attributes on every
    ``db.commit()``; passing the live row across commits leaves
    a foot-gun where ``dispatch.foo`` post-commit triggers a
    refresh on a row a parallel ``retire_event_channels`` may
    have already deleted (raising ``ObjectDeletedError``).

    The ``Event`` ORM row stays — we read multiple fields off
    it and no transaction deletes events mid-sweep, so the
    expiration risk doesn't apply."""

    # Step 1 — atomic claim. Set message_id only when the row is
    # still pending AND no message_id has been minted yet. Two
    # parallel workers fighting for the same row will only have
    # one win; the loser's claim returns 0 rows, we bail.
    message_id = new_message_id()
    claimed = (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.id == dispatch_id,
            EmailDispatch.status == EmailStatus.PENDING,
            EmailDispatch.message_id.is_(None),
        )
        .update(
            {EmailDispatch.message_id: message_id},
            synchronize_session=False,
        )
    )
    db.commit()
    if claimed == 0:
        logger.info(
            "dispatch_skipped_already_claimed",
            channel=channel.value,
            dispatch_id=dispatch_id,
        )
        return

    # Step 2 — decrypt. Failures are unrecoverable.
    try:
        plaintext = encryption.decrypt(ciphertext or b"")
    except Exception:
        logger.exception(
            "dispatch_decrypt_failed",
            channel=channel.value,
            dispatch_id=dispatch_id,
        )
        _finalise(db, channel, dispatch_id, sent=False, message_id=None, feedback_token=None)
        return

    # Step 3 — FEEDBACK mints a one-shot redemption token before
    # send. Held as a local so the failure path can drop it
    # without dict-with-private-key threading. The token never
    # references a signup — privacy contract.
    feedback_token: str | None = None
    template_context = dict(CHANNELS[channel].context(event))
    if channel == EmailChannel.FEEDBACK:
        feedback_token = secrets.token_urlsafe(32)
        db.add(
            FeedbackToken(
                token=feedback_token,
                event_id=event.id,
                expires_at=datetime.now(UTC) + FEEDBACK_TOKEN_TTL,
            )
        )
        db.commit()
        template_context["feedback_url"] = build_url(f"e/{event.slug}/feedback", t=feedback_token)

    sent = send_with_retry(
        to=plaintext,
        template_name=CHANNELS[channel].template,
        context=template_context,
        locale=event.locale,
        message_id=message_id,
        log_event=f"{channel.value}_send_failed",
    )

    _finalise(
        db,
        channel,
        dispatch_id,
        sent=sent,
        message_id=message_id if sent else None,
        feedback_token=feedback_token,
    )


def _finalise(
    db: Session,
    channel: EmailChannel,
    dispatch_id: str,
    *,
    sent: bool,
    message_id: str | None,
    feedback_token: str | None,
) -> None:
    """Conditional status flip + null the ciphertext + drop the
    feedback token on failure. The status UPDATE is filtered on
    ``status='pending'`` so a parallel worker / toggle-off cleanup
    that flipped the row out from under us isn't stomped.

    The same UPDATE that transitions to a terminal state nulls
    ``encrypted_email``: under the dispatch-owns-its-address
    contract, finalising *is* the wipe."""
    new_status = EmailStatus.SENT if sent else EmailStatus.FAILED
    updated = (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.id == dispatch_id,
            EmailDispatch.status == EmailStatus.PENDING,
        )
        .update(
            {
                EmailDispatch.status: new_status,
                EmailDispatch.sent_at: datetime.now(UTC),
                EmailDispatch.message_id: message_id,
                EmailDispatch.encrypted_email: None,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        # Status moved out from under us — drop any feedback
        # token we minted; the email never went out so the link
        # is unredeemable in practice.
        _drop_feedback_token(db, feedback_token)
        logger.info(
            "dispatch_skipped_status_changed",
            channel=channel.value,
            dispatch_id=dispatch_id,
        )
        return

    if not sent:
        _drop_feedback_token(db, feedback_token)

    logger.info(
        "dispatch_processed",
        channel=channel.value,
        dispatch_id=dispatch_id,
        sent=sent,
    )
    emit_metric(channel=channel.value, outcome="sent" if sent else "failed")


def _run_with_filter(channel: EmailChannel, extra_filters: list[Any]) -> int:
    """Body shared by ``run_once`` and ``run_for_event``. Selects
    a batch of pending (dispatch_id, ciphertext, event) triples
    for one channel and processes each through the lifecycle.

    Returns the count of rows picked up. Ordered by
    ``dispatch.id`` (uuid7) so a batch limit doesn't starve
    later rows across ticks — earliest-claimed first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(EmailDispatch.id, EmailDispatch.encrypted_email, Event)
            .join(Event, Event.id == EmailDispatch.event_id)
            .filter(
                EmailDispatch.channel == channel,
                EmailDispatch.status == EmailStatus.PENDING,
                EmailDispatch.encrypted_email.is_not(None),
                *extra_filters,
            )
            .order_by(EmailDispatch.id)
            .limit(email_batch_size())
            .all()
        )
        for dispatch_id, ciphertext, event in rows:
            _process_one(db, channel, event, dispatch_id, ciphertext)
        db.commit()
        return len(rows)
    finally:
        db.close()


def run_once(channel: EmailChannel) -> int:
    """Hourly cron sweep. Picks up every pending dispatch for the
    channel whose event currently satisfies the channel's window
    predicate (e.g. "starts in <72h" for reminder).

    Sized by ``EMAIL_BATCH_SIZE`` (default 200)."""
    now = datetime.now(UTC)
    cdef = CHANNELS[channel]
    return _run_with_filter(
        channel,
        [
            cdef.toggle.is_(True),
            cdef.window(now),
        ],
    )


def run_for_event(channel: EmailChannel, event_id: str) -> int:
    """Manual trigger: process every still-pending dispatch on
    one specific event for a given channel. Used by the
    organiser-side "send X now" button. Skips the window
    predicate (the organiser is asking explicitly) but still
    requires the per-event toggle to be on."""
    return _run_with_filter(
        channel,
        [
            Event.id == event_id,
            CHANNELS[channel].toggle.is_(True),
        ],
    )


# --- Reapers ------------------------------------------------------


def reap_partial_sends(db: Session) -> int:
    """Sweep dispatches stuck at ``pending`` with a message_id —
    those crashed mid-send. Flip to ``failed`` so the regular
    worker query no longer returns them; the same UPDATE nulls
    ``encrypted_email`` (finalising is the wipe)."""
    now = datetime.now(UTC)
    reaped = (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.status == EmailStatus.PENDING,
            EmailDispatch.message_id.is_not(None),
        )
        .update(
            {
                EmailDispatch.status: EmailStatus.FAILED,
                EmailDispatch.sent_at: now,
                EmailDispatch.encrypted_email: None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if reaped:
        logger.warning("reaped_partial_sends", count=reaped)
    return reaped


def retire_event_channels(
    db: Session,
    *,
    event_id: str,
    channels: set[EmailChannel],
) -> None:
    """An organiser flipped one or more channels off on this
    event. Delete pending dispatches for the affected channels;
    leave any in-flight sends (``message_id IS NOT NULL``) alone
    — those will finalise on their own. The deleted rows take
    their ``encrypted_email`` with them."""
    if not channels:
        return
    db.query(EmailDispatch).filter(
        EmailDispatch.event_id == event_id,
        EmailDispatch.channel.in_(channels),
        EmailDispatch.status == EmailStatus.PENDING,
        EmailDispatch.message_id.is_(None),
    ).delete(synchronize_session=False)


def reap_expired() -> int:
    """Daily reaper. Finalises any pending dispatch whose channel
    window has long passed:

    * REMINDER — event ``starts_at <= now``; the regular sweep
      won't pick these up (its window predicate excludes events
      whose ``starts_at`` is already in the past).
    * FEEDBACK — event ``ends_at <= now - POST_EVENT_PURGE_DELAY``.

    Sets status=FAILED, sent_at=now, encrypted_email=NULL in one
    UPDATE so the privacy contract holds even when every other
    path failed (worker bug, dropped commit, multi-day cron
    outage). Keeps the terminal-state row rather than DELETEing
    so the dispatches table stays a complete history of "what we
    tried to send."

    Under normal operation this is a near-no-op — the regular
    worker sweep finalises rows long before they hit this reaper.
    A non-zero return is a signal that something else is broken;
    the warning log surfaces it."""
    now = datetime.now(UTC)
    feedback_cutoff = now - POST_EVENT_PURGE_DELAY
    db = SessionLocal()
    try:
        event_window_closed = (
            db.query(Event.id)
            .filter(
                Event.id == EmailDispatch.event_id,
                ((EmailDispatch.channel == EmailChannel.REMINDER) & (Event.starts_at <= now))
                | ((EmailDispatch.channel == EmailChannel.FEEDBACK) & (Event.ends_at <= feedback_cutoff)),
            )
            .exists()
        )
        finalised = (
            db.query(EmailDispatch)
            .filter(
                EmailDispatch.status == EmailStatus.PENDING,
                event_window_closed,
            )
            .update(
                {
                    EmailDispatch.status: EmailStatus.FAILED,
                    EmailDispatch.sent_at: now,
                    EmailDispatch.encrypted_email: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if finalised:
            logger.warning("reaped_expired_dispatches", count=finalised)
        return finalised
    finally:
        db.close()


# Discoverability for callers that iterate channels (organiser
# previews, retire-on-toggle).
ALL_CHANNELS: tuple[EmailChannel, ...] = (EmailChannel.REMINDER, EmailChannel.FEEDBACK)
