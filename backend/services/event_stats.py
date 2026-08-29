"""Event read aggregates.

Helpers the events routers compose:

* ``list_enrich`` / ``enrich`` — batched chapter-name + booking headcount
  + next-occurrence lookup, turning ORM ``Event`` rows into the list DTO
  and the full one. ``archived_enrich`` does the same from the archive
  twin. All three are batched: one query per fact for the whole page,
  never one per row.
* ``occurrence_totals`` / ``occurrence_signup_counts`` — per-occurrence
  headcount + line-item counts, for the organiser occurrence panel and
  the public agenda.
* ``occurrence_signups_summary`` — name + party_size + help_choices for
  one occurrence's line items. Privacy-bounded: never email, source, or
  feedback-email status.

Routers stay thin; the SQL lives here where it can be unit-tested.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Event, Occurrence, Registration, Signup
from ..schemas.events import EventListOut, EventOut, EventStatsOut, SignupSummaryOut
from . import archive
from . import image as image_svc
from .events import now_wallclock


def registration_totals(db: Session, event_ids: list[str]) -> dict[str, int]:
    """``event_id -> SUM(party_size)`` over the event's bookings — how many
    people signed up for the course, each booking counted once regardless
    of how many sessions it covers."""
    if not event_ids:
        return {}
    return {
        event_id: int(total or 0)
        for event_id, total in (
            db.query(Registration.event_id, func.coalesce(func.sum(Registration.party_size), 0))
            .filter(Registration.event_id.in_(event_ids))
            .group_by(Registration.event_id)
            .all()
        )
    }


def occurrence_totals(db: Session, occurrence_ids: list[str]) -> dict[str, int]:
    """``occurrence_id -> SUM(party_size)`` over the registrations that have
    a line item on the occurrence — that session's headcount. Shared by the
    organiser occurrence panel and the public agenda so headcount is
    computed one way."""
    if not occurrence_ids:
        return {}
    return {
        occ_id: int(total or 0)
        for occ_id, total in (
            db.query(Signup.occurrence_id, func.coalesce(func.sum(Registration.party_size), 0))
            .join(Registration, Registration.id == Signup.registration_id)
            .filter(Signup.occurrence_id.in_(occurrence_ids))
            .group_by(Signup.occurrence_id)
            .all()
        )
    }


def occurrence_signup_counts(db: Session, occurrence_ids: list[str]) -> dict[str, int]:
    """``occurrence_id -> COUNT(line items)`` for the given occurrences."""
    if not occurrence_ids:
        return {}
    return {
        occ_id: int(n or 0)
        for occ_id, n in (
            db.query(Signup.occurrence_id, func.count(Signup.id))
            .filter(Signup.occurrence_id.in_(occurrence_ids))
            .group_by(Signup.occurrence_id)
            .all()
        )
    }


def _next_occurrence(db: Session, event_ids: list[str], now: datetime) -> dict[str, tuple[datetime | None, str]]:
    """``event_id -> (next_starts_at, link_slug)``. ``next_starts_at`` is the
    soonest occurrence that hasn't ended (``None`` when every session is
    past). ``link_slug`` is that same first-upcoming occurrence's public
    slug, falling back to the most recent past occurrence's slug so the
    dashboard card + detail header always have a working link/QR target."""
    if not event_ids:
        return {}
    rows = (
        db.query(Occurrence.event_id, Occurrence.starts_at, Occurrence.ends_at, Occurrence.slug)
        .filter(Occurrence.event_id.in_(event_ids))
        .all()
    )
    by_event: dict[str, list[tuple[datetime, datetime, str]]] = {}
    for eid, starts, ends, slug in rows:
        by_event.setdefault(eid, []).append((starts, ends, slug))
    out: dict[str, tuple[datetime | None, str]] = {}
    for eid, occs in by_event.items():
        occs.sort(key=lambda t: t[0])
        upcoming = [(s, slug) for s, e, slug in occs if e > now]
        if upcoming:
            out[eid] = (upcoming[0][0], upcoming[0][1])
        else:
            out[eid] = (None, occs[-1][2])  # all past: link to the most recent one
    return out


def link_slug(db: Session, event_id: str) -> str:
    """The occurrence one event's share link points at, the same slug the
    dashboard card and the detail header use. ``/e/{slug}`` is per
    occurrence; an event's own slug is organiser-internal and is never a
    public URL. Creating an event materialises at least its first
    session, so there is always one to point at."""
    return _next_occurrence(db, [event_id], now_wallclock())[event_id][1]


def _chapter_names(db: Session, chapter_ids: set[str]) -> dict[str, str]:
    """Live chapter id → name, batched. Soft-deleted chapters drop out,
    so the name is then ``None`` at the call site — the same rule every
    other list obeys."""
    if not chapter_ids:
        return {}
    rows = db.query(Chapter.id, Chapter.name).filter(Chapter.id.in_(chapter_ids), Chapter.deleted_at.is_(None)).all()
    return {cid: name for cid, name in rows}


def _derived(db: Session, events: list[Event]) -> tuple[dict[str, str], dict[str, int], dict]:
    """The three batched lookups both enrichers need: chapter names,
    booking headcount, and the next occurrence."""
    event_ids = [e.id for e in events]
    return (
        _chapter_names(db, {e.chapter_id for e in events if e.chapter_id}),
        registration_totals(db, event_ids),
        _next_occurrence(db, event_ids, now_wallclock()),
    )


def list_enrich(db: Session, events: list[Event]) -> list[EventListOut]:
    """The list DTO: what a dashboard card draws. Same batched lookups as
    ``enrich``, minus every field only the event's own page reads."""
    if not events:
        return []
    names, totals, next_occ = _derived(db, events)
    return [
        EventListOut(
            id=e.id,
            name_nl=e.name_nl,
            name_en=e.name_en,
            locale=e.locale,
            chapter_id=e.chapter_id,
            chapter_name=names.get(e.chapter_id) if e.chapter_id else None,
            archived=e.archived_at is not None,
            location=e.location,
            latitude=e.latitude,
            longitude=e.longitude,
            starts_on=e.starts_on,
            start_time=e.start_time,
            period_weeks=e.period_weeks,
            cycle_slots=e.cycle_slots,
            span_weeks=e.span_weeks,
            next_starts_at=next_occ.get(e.id, (None, None))[0],
            next_slug=next_occ.get(e.id, (None, None))[1],
            attendee_count=int(totals.get(e.id, 0)),
        )
        for e in events
    ]


def enrich(db: Session, events: list[Event]) -> list[EventOut]:
    """The full DTO: the list fields plus the sign-up form's own
    definition. Single-event endpoints wrap a 1-list and unwrap the
    result."""
    if not events:
        return []
    chapter_names, totals, next_occ = _derived(db, events)

    return [
        EventOut(
            id=e.id,
            slug=e.slug,
            name_nl=e.name_nl,
            name_en=e.name_en,
            topic_nl=e.topic_nl,
            topic_en=e.topic_en,
            location=e.location,
            latitude=e.latitude,
            longitude=e.longitude,
            starts_on=e.starts_on,
            start_time=e.start_time,
            end_time=e.end_time,
            period_weeks=e.period_weeks,
            cycle_slots=e.cycle_slots,
            span_weeks=e.span_weeks,
            horizon_days=e.horizon_days,
            source_options=e.source_options,
            source_enabled=e.source_enabled,
            help_options=e.help_options,
            help_enabled=e.help_enabled,
            feedback_enabled=e.feedback_enabled,
            reminder_enabled=e.reminder_enabled,
            listed=e.listed,
            name_required=e.name_required,
            answers_editable=e.answers_editable,
            locale=e.locale,
            chapter_id=e.chapter_id,
            chapter_name=chapter_names.get(e.chapter_id) if e.chapter_id else None,
            image_url=image_svc.public_url(e.image_path),
            image_artist_instagram=e.image_artist_instagram,
            next_starts_at=next_occ.get(e.id, (None, None))[0],
            next_slug=next_occ.get(e.id, (None, None))[1],
            attendee_count=int(totals.get(e.id, 0)),
            archived=e.archived_at is not None,
        )
        for e in events
    ]


def archived_enrich(db: Session, rows: list[Mapping[str, Any]]) -> list[EventListOut]:
    """The same list DTO for events that have left the live tables.

    Columns come from the archive twin, the headcount from the archived
    registrations, and the chapter name from ``chapters``, which is still
    live. There is no next occurrence for an archived event, and saying
    ``None`` is more honest than computing one from dates nobody will act
    on.

    Batched like every other archived list: two queries for the page,
    not two per row.
    """
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    names = _chapter_names(db, {r["chapter_id"] for r in rows if r["chapter_id"]})
    totals = archive.child_sums(db, "registrations", "event_id", "party_size", ids)
    return [
        EventListOut(
            **{
                key: r[key]
                for key in (
                    "id",
                    "name_nl",
                    "name_en",
                    "locale",
                    "chapter_id",
                    "location",
                    "latitude",
                    "longitude",
                    "starts_on",
                    "start_time",
                    "period_weeks",
                    "cycle_slots",
                    "span_weeks",
                )
            },
            chapter_name=names.get(r["chapter_id"]) if r["chapter_id"] else None,
            next_starts_at=None,
            next_slug=None,
            attendee_count=totals.get(r["id"], 0),
            archived=True,
        )
        for r in rows
    ]


def to_out(db: Session, event: Event) -> EventOut:
    """Single-event convenience — wraps ``enrich`` for a 1-list."""
    return enrich(db, [event])[0]


def _stats_for(db: Session, *, help_options: list[str], signup_filter) -> EventStatsOut:
    """Source/help breakdowns over the line items matching ``signup_filter``
    (an event's occurrences, or a single occurrence). Both breakdowns count
    people, not line items: a booking of three that ticked "Opbouwen" is
    three helpers, so the columns add up to ``total_attendees``. Aggregated
    only: the ``by_source`` counts never link a source answer to a person."""
    rows = (
        db.query(Signup.source_choice, func.count(Signup.id), func.coalesce(func.sum(Registration.party_size), 0))
        .join(Occurrence, Occurrence.id == Signup.occurrence_id)
        .join(Registration, Registration.id == Signup.registration_id)
        .filter(signup_filter)
        .group_by(Signup.source_choice)
        .all()
    )
    total_signups = sum(int(c) for _, c, _ in rows)
    total_attendees = sum(int(s or 0) for _, _, s in rows)
    by_source = {src: int(s or 0) for src, _, s in rows if src is not None}

    by_help: dict[str, int] = {opt: 0 for opt in help_options}
    if help_options:
        choice_lists = (
            db.query(Signup.help_choices, Registration.party_size)
            .join(Occurrence, Occurrence.id == Signup.occurrence_id)
            .join(Registration, Registration.id == Signup.registration_id)
            .filter(signup_filter)
        ).all()
        for choices, party_size in choice_lists:
            for choice in choices or []:
                if choice in by_help:
                    by_help[choice] += int(party_size or 0)

    return EventStatsOut(
        total_signups=total_signups,
        total_attendees=total_attendees,
        by_source=by_source,
        by_help=by_help,
    )


def per_occurrence_stats(db: Session, occurrence: Occurrence, help_options: list[str]) -> EventStatsOut:
    """The same source/help breakdown scoped to one occurrence — the "stats
    of that day" behind the detail page's calendar day switcher."""
    return _stats_for(db, help_options=help_options, signup_filter=Signup.occurrence_id == occurrence.id)


def occurrence_signups_summary(db: Session, occurrence: Occurrence) -> list[SignupSummaryOut]:
    """Per-line-item list for one occurrence on the organiser details page.
    Name + headcount come from the parent booking; help-choices from the
    line item. Never email, source, or feedback-email status."""
    rows = (
        db.query(
            Signup.id,
            Signup.registration_id,
            Registration.display_name,
            Registration.party_size,
            Registration.link_recovered_at,
            Signup.help_choices,
        )
        .join(Registration, Registration.id == Signup.registration_id)
        .filter(Signup.occurrence_id == occurrence.id)
        .order_by(Signup.created_at.asc())
        .all()
    )
    return [
        SignupSummaryOut(
            id=sid,
            registration_id=rid,
            display_name=name,
            party_size=size,
            link_recovered_at=recovered,
            help_choices=help_choices or [],
        )
        for sid, rid, name, size, recovered, help_choices in rows
    ]
