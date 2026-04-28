"""Declarative descriptions of email channels.

A ``ChannelSpec`` captures everything that distinguishes one
email channel from another:

* the templates / context keys it expects;
* the SQL predicate that selects events whose channel is
  currently due (``select_due_events``);
* the per-event ``Event`` toggle column;
* per-channel hooks for token minting / cleanup.

The generic worker in ``services.email_dispatcher`` parameterises
over these specs. Adding a new channel is a single
``ChannelSpec(...)`` constant — no new worker file, no new
schema columns, no new APScheduler job (the channel name plumbs
through into the existing per-channel sweep loop).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import EmailChannel, Event, Signup

# How long a feedback link in an email stays redeemable.
FEEDBACK_TOKEN_TTL = timedelta(days=30)
# Reminders fire when the event is within this window of starting.
REMINDER_WINDOW = timedelta(hours=72)
# Feedback fires this long after an event ended.
FEEDBACK_DELAY = timedelta(hours=24)


# ---- ChannelSpec --------------------------------------------------


@dataclass(frozen=True)
class ChannelSpec:
    """Per-channel knobs the generic dispatcher needs."""

    channel: EmailChannel
    template_name: str
    # The mapped Event column that gates whether an event
    # participates in this channel at all (e.g.
    # ``Event.reminder_enabled``). Typed as ``Any`` because
    # SQLAlchemy's ``InstrumentedAttribute`` doesn't fit into a
    # frozen dataclass field cleanly.
    event_toggle: Any
    # ``window_predicate(now)`` returns a SQLAlchemy predicate
    # that's True for events whose channel is due *now*.
    window_predicate: Callable[[datetime], Any]
    # Build the Jinja context dict from an Event row.
    build_context: Callable[[Event], dict[str, Any]]
    # Optional per-channel hooks. Feedback uses these to mint and
    # clean up its in-email redemption token.
    on_pre_send: Callable[[Session, Signup, Event], dict[str, Any]] | None = None
    on_failure: Callable[[Session, Signup, dict[str, Any]], None] | None = None
    on_success: Callable[[Session, Signup, dict[str, Any]], None] | None = None


# ---- The two channels --------------------------------------------


def _reminder_window(now: datetime) -> Any:
    """Reminder fires while ``now < event.starts_at <= now+72h``."""
    return (Event.starts_at > now) & (Event.starts_at <= now + REMINDER_WINDOW)


_DAY_NAMES = {
    "nl": ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
_MONTH_NAMES = {
    "nl": [
        "januari", "februari", "maart", "april", "mei", "juni",
        "juli", "augustus", "september", "oktober", "november", "december",
    ],
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
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
    """24-hour HH:MM–HH:MM. Same format in both locales — the NL
    audience reads 24h, the EN audience reads it just fine too."""
    return f"{starts_at:%H:%M}–{ends_at:%H:%M}"


def _osm_url(event: Event) -> str:
    """Pin-on-map URL when we have coordinates; fall back to a
    text search by ``location`` so the link still goes somewhere
    useful for events imported without geocoding."""
    from urllib.parse import quote

    if event.latitude is not None and event.longitude is not None:
        return (
            f"https://www.openstreetmap.org/?mlat={event.latitude}"
            f"&mlon={event.longitude}#map=17/{event.latitude}/{event.longitude}"
        )
    return f"https://www.openstreetmap.org/search?query={quote(event.location)}"


def _reminder_context(event: Event) -> dict[str, Any]:
    from .email.urls import build_url

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


REMINDER = ChannelSpec(
    channel=EmailChannel.REMINDER,
    template_name="reminder.html",
    event_toggle=Event.reminder_enabled,
    window_predicate=_reminder_window,
    build_context=_reminder_context,
)


def _feedback_window(now: datetime) -> Any:
    """Feedback fires when the event ended ≥24h ago."""
    return Event.ends_at <= now - FEEDBACK_DELAY


def _feedback_context(event: Event) -> dict[str, Any]:
    # Built lazily — the URL depends on the per-signup
    # FeedbackToken minted in the on_pre_send hook below.
    return {"event_name": event.name}


def _feedback_pre_send(db: Session, signup: Signup, event: Event) -> dict[str, Any]:
    """Mint a one-time FeedbackToken and embed it in the
    template URL. Returned dict is merged into the template
    context and also threaded into ``on_failure`` so we can drop
    the token if SMTP rejects every retry."""
    import secrets

    from ..models import FeedbackToken
    from .email.urls import build_url

    token = secrets.token_urlsafe(32)
    db.add(
        FeedbackToken(
            token=token,
            signup_id=signup.id,
            event_id=event.entity_id,
            expires_at=datetime.now(UTC) + FEEDBACK_TOKEN_TTL,
        )
    )
    db.flush()
    return {
        "feedback_url": build_url(f"e/{event.slug}/feedback", t=token),
        # Hand-back so ``on_failure`` / ``on_success`` can find it.
        "_token": token,
    }


def _feedback_drop_token(db: Session, signup: Signup, hook_state: dict[str, Any]) -> None:
    """SMTP failed; the token is unredeemable in practice
    (recipient never got the link) — drop it so it doesn't sit
    in the table for 30d."""
    from ..models import FeedbackToken

    token = hook_state.get("_token")
    if token:
        db.query(FeedbackToken).filter(FeedbackToken.token == token).delete()


FEEDBACK = ChannelSpec(
    channel=EmailChannel.FEEDBACK,
    template_name="feedback.html",
    event_toggle=Event.questionnaire_enabled,
    window_predicate=_feedback_window,
    build_context=_feedback_context,
    on_pre_send=_feedback_pre_send,
    on_failure=_feedback_drop_token,
)


# Registry — used by ``backend/worker.py`` to schedule one
# sweep job per channel.
ALL_CHANNELS: tuple[ChannelSpec, ...] = (REMINDER, FEEDBACK)


def spec_for(channel: EmailChannel) -> ChannelSpec:
    for spec in ALL_CHANNELS:
        if spec.channel == channel:
            return spec
    raise KeyError(channel)
