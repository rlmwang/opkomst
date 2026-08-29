"""Datepolls-feature service helpers.

Mirrors ``services/forms.py``: ``enrich`` / ``to_out`` /
``to_public_out`` DTO projections, ``apply_slots`` (the candidate-slot
diff, matched on the natural key ``(on_date, start_time, end_time)``),
and the organiser-side reads ``slot_aggregates`` /
``submission_count`` / ``submissions``.

Chapter-scoped lookups live in ``services.access``
(``get_datepoll_for_user`` / ``datepoll_scope_filter``).
"""

from collections.abc import Iterator, Mapping, Sequence
from datetime import date, time
from typing import TYPE_CHECKING, Any, Final, get_args

from sqlalchemy import and_, distinct, func, select, text
from sqlalchemy.orm import Session

from ..models import Chapter, Datepoll, DatepollResponse, DatepollSlot, DatepollSubmission, User
from ..schemas.datepolls import (
    Availability,
    DatepollListOut,
    DatepollOut,
    DatepollSlotOut,
    DatepollSlotSummary,
    DatepollSubmissionOut,
    PublicDatepollOut,
)
from . import access, tenancy
from . import archive as archive_svc
from . import image as image_svc

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
    tenancy.bind(poll.tenant_id, poll.tenant.brand_slug)
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


# The columns the projections below read. A GET selects exactly these;
# a write route hands over the ORM entity it just saved, which answers
# the same attribute names, so one projection serves both.
LIST_COLUMNS = (
    Datepoll.id,
    Datepoll.slug,
    Datepoll.name_nl,
    Datepoll.name_en,
    Datepoll.locale,
    Datepoll.chapter_id,
    Datepoll.archived_at,
    Datepoll.created_at,
)
FULL_COLUMNS = (
    *LIST_COLUMNS,
    Datepoll.description_nl,
    Datepoll.description_en,
    Datepoll.location,
    Datepoll.latitude,
    Datepoll.longitude,
    Datepoll.image_path,
    Datepoll.image_artist_instagram,
    Datepoll.name_required,
    Datepoll.answers_editable,
)


def list_for_user(db: Session, user: User, chapter_id: str | None) -> list[DatepollListOut]:
    """The organiser's poll list, in one statement.

    ``date_count`` counts distinct candidate days, not slots: a day with
    three time-slots is still one day in the list summary. All three
    date facts are scalar subqueries, so one poll stays one row."""
    days = select(func.count(distinct(DatepollSlot.on_date))).where(DatepollSlot.datepoll_id == Datepoll.id)
    first = select(func.min(DatepollSlot.on_date)).where(DatepollSlot.datepoll_id == Datepoll.id)
    last = select(func.max(DatepollSlot.on_date)).where(DatepollSlot.datepoll_id == Datepoll.id)
    filled = select(func.count(DatepollSubmission.id)).where(DatepollSubmission.datepoll_id == Datepoll.id)
    rows = db.execute(
        select(
            *LIST_COLUMNS,
            Chapter.name.label("chapter_name"),
            days.scalar_subquery().label("date_count"),
            first.scalar_subquery().label("first_date"),
            last.scalar_subquery().label("last_date"),
            filled.scalar_subquery().label("submission_count"),
        )
        .select_from(Datepoll)
        .outerjoin(Chapter, and_(Chapter.id == Datepoll.chapter_id, Chapter.deleted_at.is_(None)))
        .where(access.list_filter(db, user, Datepoll, chapter_id), Datepoll.archived_at.is_(None))
        .order_by(Datepoll.created_at.desc())
    ).all()
    return [
        DatepollListOut(
            id=r.id,
            slug=r.slug,
            name_nl=r.name_nl,
            name_en=r.name_en,
            locale=r.locale,
            chapter_id=r.chapter_id,
            chapter_name=r.chapter_name,
            archived=r.archived_at is not None,
            created_at=r.created_at,
            date_count=int(r.date_count or 0),
            first_date=r.first_date,
            last_date=r.last_date,
            submission_count=int(r.submission_count or 0),
        )
        for r in rows
    ]


def enrich(db: Session, polls: Sequence[Any]) -> list[DatepollListOut]:
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

    sub_counts = {
        pid: int(n)
        for pid, n in db.query(DatepollSubmission.datepoll_id, func.count(DatepollSubmission.id))
        .filter(DatepollSubmission.datepoll_id.in_(poll_ids))
        .group_by(DatepollSubmission.datepoll_id)
        .all()
    }

    return [
        DatepollListOut(
            id=p.id,
            slug=p.slug,
            name_nl=p.name_nl,
            name_en=p.name_en,
            locale=p.locale,
            chapter_id=p.chapter_id,
            chapter_name=names.get(p.chapter_id) if p.chapter_id else None,
            archived=p.archived_at is not None,
            created_at=p.created_at,
            date_count=summary.get(p.id, (0, None, None))[0],
            first_date=summary.get(p.id, (0, None, None))[1],
            last_date=summary.get(p.id, (0, None, None))[2],
            submission_count=sub_counts.get(p.id, 0),
        )
        for p in polls
    ]


def archived_enrich(db: Session, rows: list[Mapping[str, Any]]) -> list[DatepollListOut]:
    """The same DTO for polls that have left the live tables: columns
    from the twin, the date summary and submission count from the
    archived slots and submissions."""
    if not rows:
        return []
    names = _chapter_names(db, {r["chapter_id"] for r in rows if r["chapter_id"]})
    poll_ids = [r["id"] for r in rows]
    slots = archive_svc.archive_metadata.tables["datepoll_slots_archive"]
    summary: dict[str, tuple[int, date | None, date | None]] = {}
    for pid, count, first, last in db.execute(
        select(
            slots.c.datepoll_id,
            func.count(distinct(slots.c.on_date)),
            func.min(slots.c.on_date),
            func.max(slots.c.on_date),
        )
        .where(slots.c.datepoll_id.in_(poll_ids))
        .group_by(slots.c.datepoll_id)
    ):
        summary[pid] = (int(count), first, last)
    sub_counts = archive_svc.child_counts(db, "datepoll_submissions", "datepoll_id", poll_ids)
    return [
        DatepollListOut(
            id=r["id"],
            slug=r["slug"],
            name_nl=r["name_nl"],
            name_en=r["name_en"],
            locale=r["locale"],
            chapter_id=r["chapter_id"],
            chapter_name=names.get(r["chapter_id"]) if r["chapter_id"] else None,
            archived=True,
            created_at=r["created_at"],
            date_count=summary.get(r["id"], (0, None, None))[0],
            first_date=summary.get(r["id"], (0, None, None))[1],
            last_date=summary.get(r["id"], (0, None, None))[2],
            submission_count=sub_counts.get(r["id"], 0),
        )
        for r in rows
    ]


def _slots(db: Session, datepoll_id: str) -> Sequence[Any]:
    """Candidate slots in display order: by date, then whole-day
    (NULL start) before timed, then by start time."""
    return db.execute(
        select(*DatepollSlot.__table__.c)
        .where(DatepollSlot.datepoll_id == datepoll_id)
        .order_by(DatepollSlot.on_date, DatepollSlot.start_time.nulls_first())
    ).all()


def to_out(db: Session, poll: Any) -> DatepollOut:
    """Single-poll organiser DTO: list-row fields + description + the
    full candidate-slot list. One chapter lookup + one slot query."""
    chapter_name = _chapter_names(db, {poll.chapter_id}).get(poll.chapter_id) if poll.chapter_id else None
    slots = _slots(db, poll.id)
    days = sorted({s.on_date for s in slots})
    return DatepollOut(
        id=poll.id,
        slug=poll.slug,
        name_nl=poll.name_nl,
        name_en=poll.name_en,
        locale=poll.locale,
        chapter_id=poll.chapter_id,
        chapter_name=chapter_name,
        archived=poll.archived_at is not None,
        created_at=poll.created_at,
        date_count=len(days),
        first_date=days[0] if days else None,
        last_date=days[-1] if days else None,
        submission_count=submission_count(db, poll.id),
        description_nl=poll.description_nl,
        description_en=poll.description_en,
        location=poll.location,
        latitude=poll.latitude,
        longitude=poll.longitude,
        image_url=image_svc.public_url(poll.image_path),
        image_artist_instagram=poll.image_artist_instagram,
        name_required=poll.name_required,
        answers_editable=poll.answers_editable,
        slots=[DatepollSlotOut.model_validate(s) for s in slots],
    )


def to_public_out(db: Session, poll: Datepoll) -> PublicDatepollOut:
    """Public by-slug DTO: name + description + locale + candidate
    slots in display order, nothing internal."""
    return PublicDatepollOut(
        id=poll.id,
        name_nl=poll.name_nl,
        name_en=poll.name_en,
        description_nl=poll.description_nl,
        description_en=poll.description_en,
        location=poll.location,
        latitude=poll.latitude,
        longitude=poll.longitude,
        image_url=image_svc.public_url(poll.image_path),
        image_artist_instagram=poll.image_artist_instagram,
        locale=poll.locale,
        name_required=poll.name_required,
        answers_editable=poll.answers_editable,
        slots=[DatepollSlotOut.model_validate(s) for s in _slots(db, poll.id)],
    )


# --- Organiser-side reads --------------------------------------------


def submission_count(db: Session, datepoll_id: str) -> int:
    return (
        db.query(func.count(DatepollSubmission.id)).filter(DatepollSubmission.datepoll_id == datepoll_id).scalar() or 0
    )


def slot_aggregates(db: Session, datepoll_id: str, total_subs: int) -> tuple[list[DatepollSlotSummary], str | None]:
    """Per-slot yes/maybe/no tallies and the winning slot id (most yes,
    tie-break fewest no, ``None`` when there are no responses at all).

    ``total_subs`` is the respondent pool the blanks are measured
    against, passed in because the page that asks for these tallies
    prints the same number next to them and counted it already."""
    slots = _slots(db, datepoll_id)
    slot_ids = [s.id for s in slots]
    if not slot_ids:
        return [], None

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

    # Best slot: most yes, then most maybe, then most "not filled"
    # (submissions that didn't answer this slot) — ``no`` is ignored,
    # so an explicit no never helps a slot place.
    total_responses = sum(s.yes + s.maybe + s.no for s in summaries)
    best_slot_id: str | None = None
    if total_responses:
        best = max(summaries, key=lambda s: (s.yes, s.maybe, total_subs - s.yes - s.maybe - s.no))
        best_slot_id = best.id

    return summaries, best_slot_id


# The candidate dates, in the order the poll asks them, each with the
# heading its column gets. A whole-day slot is named by its date alone;
# a timed one carries the range, on the 24-hour clock every reader of a
# spreadsheet can line up against the next file.
_SLOT_COLUMNS_SQL = text(
    """
SELECT id,
       to_char(on_date, 'YYYY-MM-DD')
       || coalesce(' ' || to_char(start_time, 'HH24:MI') || '-' || to_char(end_time, 'HH24:MI'), '') AS heading
FROM datepoll_slots
WHERE datepoll_id = :datepoll_id
ORDER BY on_date, start_time NULLS FIRST, end_time NULLS FIRST
"""
)

# One row per submission, its answers already in column order. The slot
# ids are unnested with their position, so a date somebody left unset is
# an empty cell rather than a short row.
_CSV_SQL = text(
    """
WITH column_of AS (
    SELECT slot_id, ordinal
    FROM unnest(cast(:slot_ids AS text[])) WITH ORDINALITY AS t(slot_id, ordinal)
)
SELECT coalesce(s.display_name, 'Anonymous') AS name,
       to_char(s.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS submitted_at,
       coalesce(s.note, '') AS note,
       (
           SELECT coalesce(array_agg(coalesce(r.availability, '') ORDER BY column_of.ordinal), '{}')
           FROM column_of
           LEFT JOIN datepoll_responses r
                  ON r.submission_id = s.id AND r.datepoll_slot_id = column_of.slot_id
       ) AS cells
FROM datepoll_submissions s
WHERE s.datepoll_id = :datepoll_id
ORDER BY s.created_at
"""
)


def submissions_csv(db: Session, datepoll_id: str) -> tuple[list[str], Iterator[Sequence[Any]]]:
    """The organiser's download: the header, and the rows behind it.

    The dates are the columns, in poll order, and the note is the last
    one. Written by the database and streamed out
    (``services/csv_export``)."""
    slots = db.execute(_SLOT_COLUMNS_SQL, {"datepoll_id": datepoll_id}).all()
    header = ["Name", "Submitted at", *(slot.heading for slot in slots), "Note"]
    result = db.execute(_CSV_SQL, {"datepoll_id": datepoll_id, "slot_ids": [slot.id for slot in slots]})
    rows = ([row.name, row.submitted_at, *row.cells, row.note] for row in result)
    return header, rows


def submissions(db: Session, datepoll_id: str) -> list[DatepollSubmissionOut]:
    """Per-submission rows, keyed by slot id.

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
            link_recovered_at=s.link_recovered_at,
        )
        for s in subs
    ]
