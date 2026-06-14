"""Datepolls-feature service helpers.

Mirrors ``services/forms.py``: ``enrich`` / ``to_out`` /
``to_public_out`` DTO projections, ``apply_slots`` (the candidate-slot
diff, matched on the natural key ``(on_date, start_time, end_time)``),
and the organiser-side reads ``slot_aggregates`` /
``submission_count`` / ``submissions``.

Chapter-scoped lookups live in ``services.access``
(``get_datepoll_for_user`` / ``datepoll_scope_filter``).
"""

from datetime import date, time
from typing import TYPE_CHECKING, Final, get_args

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..models import Chapter, Datepoll, DatepollResponse, DatepollSlot, DatepollSubmission
from ..schemas.datepolls import (
    Availability,
    DatepollListOut,
    DatepollOut,
    DatepollSlotOut,
    DatepollSlotSummary,
    DatepollSubmissionOut,
    PublicDatepollOut,
)

if TYPE_CHECKING:
    from ..schemas.datepolls import DatepollSlotIn

# Sort key for a slot's natural ordering: by date, then whole-day
# (no start time) before timed, then by start time.
_SlotKey = tuple[date, time | None, time | None]

# Single source of truth for the tri-state, derived from the literal.
ALLOWED_AVAILABILITY: Final[frozenset[str]] = frozenset(get_args(Availability))


def get_datepoll_by_slug_any(db: Session, slug: str) -> Datepoll | None:
    """Slug lookup including archived polls — used by the public HTML
    route. Returns ``None`` when the slug is unknown OR archived; the
    public mini-app treats both as "no longer available", matching the
    410 the JSON endpoint returns."""
    poll = db.query(Datepoll).filter(Datepoll.slug == slug).first()
    if poll is None or poll.archived_at is not None:
        return None
    return poll


def _slot_key(on_date: date, start_time: time | None, end_time: time | None) -> _SlotKey:
    return (on_date, start_time, end_time)


def apply_slots(db: Session, datepoll_id: str, slots: list["DatepollSlotIn"]) -> None:
    """Diff-apply the candidate-slot set, matched on the natural key
    ``(on_date, start_time, end_time)``. New slots insert; slots still
    present are left untouched (so their responses survive an edit);
    slots absent from the payload are deleted (the FK cascade takes
    their responses). Caller commits."""
    existing = {
        _slot_key(s.on_date, s.start_time, s.end_time): s
        for s in db.query(DatepollSlot).filter(DatepollSlot.datepoll_id == datepoll_id).all()
    }
    wanted = {_slot_key(s.on_date, s.start_time, s.end_time): s for s in slots}

    for key, s in wanted.items():
        if key not in existing:
            db.add(
                DatepollSlot(
                    datepoll_id=datepoll_id,
                    on_date=s.on_date,
                    start_time=s.start_time,
                    end_time=s.end_time,
                )
            )

    for key, row in existing.items():
        if key not in wanted:
            db.delete(row)
    db.flush()


# --- DTO projections -------------------------------------------------


def _chapter_names(db: Session, chapter_ids: set[str]) -> dict[str, str]:
    if not chapter_ids:
        return {}
    rows = db.query(Chapter.id, Chapter.name).filter(Chapter.id.in_(chapter_ids), Chapter.deleted_at.is_(None)).all()
    return {cid: name for cid, name in rows}


def enrich(db: Session, polls: list[Datepoll]) -> list[DatepollListOut]:
    """Build ``DatepollListOut`` rows with batched lookups: one query
    for chapter names, one grouped query for the per-poll date
    count + earliest/latest. No N+1 regardless of list size."""
    if not polls:
        return []
    names = _chapter_names(db, {p.chapter_id for p in polls if p.chapter_id})
    poll_ids = [p.id for p in polls]
    summary: dict[str, tuple[int, date | None, date | None]] = {}
    # ``date_count`` counts distinct candidate days, not slots — a day
    # with three time-slots is still one day in the list summary.
    rows = (
        db.query(
            DatepollSlot.datepoll_id,
            func.count(distinct(DatepollSlot.on_date)),
            func.min(DatepollSlot.on_date),
            func.max(DatepollSlot.on_date),
        )
        .filter(DatepollSlot.datepoll_id.in_(poll_ids))
        .group_by(DatepollSlot.datepoll_id)
        .all()
    )
    for pid, count, first, last in rows:
        summary[pid] = (int(count), first, last)

    return [
        DatepollListOut(
            id=p.id,
            slug=p.slug,
            name=p.name,
            locale=p.locale,
            chapter_id=p.chapter_id,
            chapter_name=names.get(p.chapter_id) if p.chapter_id else None,
            archived=p.archived_at is not None,
            created_at=p.created_at,
            date_count=summary.get(p.id, (0, None, None))[0],
            first_date=summary.get(p.id, (0, None, None))[1],
            last_date=summary.get(p.id, (0, None, None))[2],
        )
        for p in polls
    ]


def _slots(db: Session, datepoll_id: str) -> list[DatepollSlot]:
    """Candidate slots in display order: by date, then whole-day
    (NULL start) before timed, then by start time."""
    return (
        db.query(DatepollSlot)
        .filter(DatepollSlot.datepoll_id == datepoll_id)
        .order_by(DatepollSlot.on_date, DatepollSlot.start_time.nulls_first())
        .all()
    )


def to_out(db: Session, poll: Datepoll) -> DatepollOut:
    """Single-poll organiser DTO: list-row fields + description + the
    full candidate-slot list. One chapter lookup + one slot query."""
    chapter_name = _chapter_names(db, {poll.chapter_id}).get(poll.chapter_id) if poll.chapter_id else None
    slots = _slots(db, poll.id)
    days = sorted({s.on_date for s in slots})
    return DatepollOut(
        id=poll.id,
        slug=poll.slug,
        name=poll.name,
        locale=poll.locale,
        chapter_id=poll.chapter_id,
        chapter_name=chapter_name,
        archived=poll.archived_at is not None,
        created_at=poll.created_at,
        date_count=len(days),
        first_date=days[0] if days else None,
        last_date=days[-1] if days else None,
        description=poll.description,
        image_url=poll.image_url,
        image_artist_instagram=poll.image_artist_instagram,
        slots=[DatepollSlotOut.model_validate(s) for s in slots],
    )


def to_public_out(db: Session, poll: Datepoll) -> PublicDatepollOut:
    """Public by-slug DTO: name + description + locale + candidate
    slots in display order, nothing internal."""
    return PublicDatepollOut(
        id=poll.id,
        name=poll.name,
        description=poll.description,
        image_url=poll.image_url,
        image_artist_instagram=poll.image_artist_instagram,
        locale=poll.locale,
        slots=[DatepollSlotOut.model_validate(s) for s in _slots(db, poll.id)],
    )


# --- Organiser-side reads --------------------------------------------


def submission_count(db: Session, datepoll_id: str) -> int:
    return (
        db.query(func.count(DatepollSubmission.id)).filter(DatepollSubmission.datepoll_id == datepoll_id).scalar() or 0
    )


def slot_aggregates(db: Session, datepoll_id: str) -> tuple[list[DatepollSlotSummary], str | None, list[str]]:
    """Per-slot yes/maybe/no tallies, the winning slot id (most yes,
    tie-break fewest no, ``None`` when there are no responses at all),
    and the submission notes (newest first). Comments are no longer
    per-slot — a respondent leaves one note on the whole submission."""
    slots = _slots(db, datepoll_id)
    slot_ids = [s.id for s in slots]
    if not slot_ids:
        return [], None, []

    tally: dict[str, dict[str, int]] = {sid: {"yes": 0, "no": 0, "maybe": 0} for sid in slot_ids}
    count_rows = (
        db.query(DatepollResponse.datepoll_slot_id, DatepollResponse.availability, func.count(DatepollResponse.id))
        .filter(DatepollResponse.datepoll_slot_id.in_(slot_ids))
        .group_by(DatepollResponse.datepoll_slot_id, DatepollResponse.availability)
        .all()
    )
    for slot_id, availability, count in count_rows:
        if availability in tally[slot_id]:
            tally[slot_id][availability] = int(count)

    summaries = [
        DatepollSlotSummary(
            id=s.id,
            on_date=s.on_date,
            start_time=s.start_time,
            end_time=s.end_time,
            yes=tally[s.id]["yes"],
            maybe=tally[s.id]["maybe"],
            no=tally[s.id]["no"],
        )
        for s in slots
    ]

    total_responses = sum(s.yes + s.maybe + s.no for s in summaries)
    best_slot_id: str | None = None
    if total_responses:
        best = max(summaries, key=lambda s: (s.yes, -s.no))
        best_slot_id = best.id

    note_rows = (
        db.query(DatepollSubmission.note)
        .filter(DatepollSubmission.datepoll_id == datepoll_id, DatepollSubmission.note.is_not(None))
        .order_by(DatepollSubmission.created_at.desc())
        .all()
    )
    notes = [n for (n,) in note_rows]
    return summaries, best_slot_id, notes


def submissions(db: Session, datepoll_id: str) -> list[DatepollSubmissionOut]:
    """Per-submission rows for the CSV export, keyed by slot id.

    Privacy: the submission id is opaque and the only respondent
    identifier is the self-chosen ``display_name`` (NULL = anonymous).
    """
    subs = (
        db.query(DatepollSubmission)
        .filter(DatepollSubmission.datepoll_id == datepoll_id)
        .order_by(DatepollSubmission.created_at)
        .all()
    )
    if not subs:
        return []
    sub_ids = [s.id for s in subs]
    answers: dict[str, dict[str, str]] = {sid: {} for sid in sub_ids}
    for r in db.query(DatepollResponse).filter(DatepollResponse.submission_id.in_(sub_ids)).all():
        answers[r.submission_id][r.datepoll_slot_id] = r.availability

    return [
        DatepollSubmissionOut(
            submission_id=s.id,
            display_name=s.display_name,
            note=s.note,
            created_at=s.created_at,
            answers=answers[s.id],
        )
        for s in subs
    ]
