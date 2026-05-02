"""Event read aggregates.

Three pure-ish helpers the events routers compose:

* ``enrich`` — batched chapter-name + attendee-total lookup that
  turns a list of ORM ``Event`` rows into ``EventOut`` DTOs. Used
  by every list endpoint and by the single-event paths via the
  ``to_out`` convenience wrapper.
* ``per_event_stats`` — source/help breakdowns for one event.
* ``signups_summary`` — name + party_size + help_choices, the
  organiser-side per-signup list. Privacy-bounded: never email,
  source, or feedback-email status.

Routers stay thin (input validation + auth + a small combine);
the SQL lives here where it can be unit-tested without a router
fixture, mirroring ``services/feedback_stats.py``.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Event, Signup
from ..schemas.events import EventOut, EventStatsOut, SignupSummaryOut


def enrich(db: Session, events: list[Event]) -> list[EventOut]:
    """Build ``EventOut`` DTOs with batched lookups for chapter
    names + per-event attendee totals. Always batches; single-
    event endpoints wrap a 1-list and unwrap the result. The cost
    for N=1 is the same two SELECTs the inline path used to
    issue, so single-event callers don't pay extra."""
    if not events:
        return []
    event_ids = [e.id for e in events]
    chapter_ids = sorted({e.chapter_id for e in events if e.chapter_id})

    totals: dict[str, int] = {
        event_id: int(total or 0)
        for event_id, total in (
            db.query(Signup.event_id, func.coalesce(func.sum(Signup.party_size), 0))
            .filter(Signup.event_id.in_(event_ids))
            .group_by(Signup.event_id)
            .all()
        )
    }
    chapter_names: dict[str, str] = {}
    if chapter_ids:
        rows = db.query(Chapter.id, Chapter.name).filter(Chapter.id.in_(chapter_ids)).all()
        chapter_names = {cid: name for cid, name in rows}

    return [
        EventOut(
            id=e.id,
            slug=e.slug,
            name=e.name,
            topic=e.topic,
            location=e.location,
            latitude=e.latitude,
            longitude=e.longitude,
            starts_at=e.starts_at,
            ends_at=e.ends_at,
            source_options=e.source_options,
            help_options=e.help_options,
            feedback_enabled=e.feedback_enabled,
            reminder_enabled=e.reminder_enabled,
            locale=e.locale,
            chapter_id=e.chapter_id,
            chapter_name=chapter_names.get(e.chapter_id) if e.chapter_id else None,
            attendee_count=int(totals.get(e.id, 0)),
            archived=e.archived_at is not None,
        )
        for e in events
    ]


def to_out(db: Session, event: Event) -> EventOut:
    """Single-event convenience — wraps ``enrich`` for a 1-list."""
    return enrich(db, [event])[0]


def per_event_stats(db: Session, event: Event) -> EventStatsOut:
    """Source/help breakdowns for one event. Pure SQL aggregates."""
    rows = (
        db.query(Signup.source_choice, func.count(Signup.id), func.sum(Signup.party_size))
        .filter(Signup.event_id == event.id)
        .group_by(Signup.source_choice)
        .all()
    )
    total_signups = sum(int(c) for _, c, _ in rows)
    total_attendees = sum(int(s or 0) for _, _, s in rows)
    by_source = {src: int(c) for src, c, _ in rows if src is not None}

    by_help: dict[str, int] = {opt: 0 for opt in event.help_options}
    if event.help_options:
        choice_lists = db.query(Signup.help_choices).filter(Signup.event_id == event.id).all()
        for (choices,) in choice_lists:
            for choice in choices or []:
                if choice in by_help:
                    by_help[choice] += 1

    return EventStatsOut(
        total_signups=total_signups,
        total_attendees=total_attendees,
        by_source=by_source,
        by_help=by_help,
    )


def signups_summary(db: Session, event: Event) -> list[SignupSummaryOut]:
    """Per-signup list for the organiser details page. Returns
    display_name + party_size + help_choices — never email,
    source, or feedback-email status."""
    rows = (
        db.query(Signup.id, Signup.display_name, Signup.party_size, Signup.help_choices)
        .filter(Signup.event_id == event.id)
        .order_by(Signup.created_at.asc())
        .all()
    )
    return [
        SignupSummaryOut(id=sid, display_name=name, party_size=size, help_choices=help_choices or [])
        for sid, name, size, help_choices in rows
    ]
