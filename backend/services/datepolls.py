"""Datepolls-feature service helpers.

Mirrors ``services/forms.py``: ``enrich`` / ``to_out`` /
``to_public_out`` DTO projections, ``apply_dates`` (the candidate-date
diff, matched on the natural key ``on_date``), and the organiser-side
reads ``date_aggregates`` / ``submission_count`` / ``submissions``.

Chapter-scoped lookups live in ``services.access``
(``get_datepoll_for_user`` / ``datepoll_scope_filter``).
"""

from datetime import date
from typing import TYPE_CHECKING, Final, get_args

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Datepoll, DatepollDate, DatepollResponse, DatepollSubmission
from ..schemas.datepolls import (
    Availability,
    DatepollDateOut,
    DatepollDateSummary,
    DatepollListOut,
    DatepollOut,
    DatepollSubmissionOut,
    PublicDatepollOut,
)

if TYPE_CHECKING:
    from ..schemas.datepolls import DatepollDateIn

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


def apply_dates(db: Session, datepoll_id: str, dates: list["DatepollDateIn"]) -> None:
    """Diff-apply the candidate-date set, matched on ``on_date``. New
    dates insert; dates still present are left untouched (so their
    responses survive an edit); dates absent from the payload are
    deleted (the FK cascade takes their responses). Caller commits."""
    existing = {d.on_date: d for d in db.query(DatepollDate).filter(DatepollDate.datepoll_id == datepoll_id).all()}
    wanted: set[date] = {d.on_date for d in dates}

    for on_date in wanted:
        if on_date not in existing:
            db.add(DatepollDate(datepoll_id=datepoll_id, on_date=on_date))

    for on_date, row in existing.items():
        if on_date not in wanted:
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
    rows = (
        db.query(
            DatepollDate.datepoll_id,
            func.count(DatepollDate.id),
            func.min(DatepollDate.on_date),
            func.max(DatepollDate.on_date),
        )
        .filter(DatepollDate.datepoll_id.in_(poll_ids))
        .group_by(DatepollDate.datepoll_id)
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


def _dates(db: Session, datepoll_id: str) -> list[DatepollDate]:
    return db.query(DatepollDate).filter(DatepollDate.datepoll_id == datepoll_id).order_by(DatepollDate.on_date).all()


def to_out(db: Session, poll: Datepoll) -> DatepollOut:
    """Single-poll organiser DTO: list-row fields + description + the
    full candidate-date list. One chapter lookup + one date query."""
    chapter_name = _chapter_names(db, {poll.chapter_id}).get(poll.chapter_id) if poll.chapter_id else None
    dates = _dates(db, poll.id)
    return DatepollOut(
        id=poll.id,
        slug=poll.slug,
        name=poll.name,
        locale=poll.locale,
        chapter_id=poll.chapter_id,
        chapter_name=chapter_name,
        archived=poll.archived_at is not None,
        created_at=poll.created_at,
        date_count=len(dates),
        first_date=dates[0].on_date if dates else None,
        last_date=dates[-1].on_date if dates else None,
        description=poll.description,
        dates=[DatepollDateOut.model_validate(d) for d in dates],
    )


def to_public_out(db: Session, poll: Datepoll) -> PublicDatepollOut:
    """Public by-slug DTO: name + description + locale + candidate
    dates in display order, nothing internal."""
    return PublicDatepollOut(
        id=poll.id,
        name=poll.name,
        description=poll.description,
        locale=poll.locale,
        dates=[DatepollDateOut.model_validate(d) for d in _dates(db, poll.id)],
    )


# --- Organiser-side reads --------------------------------------------


def submission_count(db: Session, datepoll_id: str) -> int:
    return (
        db.query(func.count(DatepollSubmission.id)).filter(DatepollSubmission.datepoll_id == datepoll_id).scalar() or 0
    )


def date_aggregates(db: Session, datepoll_id: str) -> tuple[list[DatepollDateSummary], str | None]:
    """Per-date yes/maybe/no tallies + date-attached comments (newest
    first), and the winning date id (most yes, tie-break fewest no,
    ``None`` when there are no responses at all)."""
    dates = _dates(db, datepoll_id)
    date_ids = [d.id for d in dates]
    if not date_ids:
        return [], None

    tally: dict[str, dict[str, int]] = {did: {"yes": 0, "no": 0, "maybe": 0} for did in date_ids}
    count_rows = (
        db.query(DatepollResponse.datepoll_date_id, DatepollResponse.availability, func.count(DatepollResponse.id))
        .filter(DatepollResponse.datepoll_date_id.in_(date_ids))
        .group_by(DatepollResponse.datepoll_date_id, DatepollResponse.availability)
        .all()
    )
    for date_id, availability, count in count_rows:
        if availability in tally[date_id]:
            tally[date_id][availability] = int(count)

    comments: dict[str, list[str]] = {did: [] for did in date_ids}
    comment_rows = (
        db.query(DatepollResponse.datepoll_date_id, DatepollResponse.comment)
        .filter(DatepollResponse.datepoll_date_id.in_(date_ids), DatepollResponse.comment.is_not(None))
        .order_by(DatepollResponse.created_at.desc())
        .all()
    )
    for date_id, comment in comment_rows:
        comments[date_id].append(comment)

    summaries = [
        DatepollDateSummary(
            id=d.id,
            on_date=d.on_date,
            yes=tally[d.id]["yes"],
            maybe=tally[d.id]["maybe"],
            no=tally[d.id]["no"],
            comments=comments[d.id],
        )
        for d in dates
    ]

    total_responses = sum(s.yes + s.maybe + s.no for s in summaries)
    best_date_id: str | None = None
    if total_responses:
        best = max(summaries, key=lambda s: (s.yes, -s.no))
        best_date_id = best.id
    return summaries, best_date_id


def submissions(db: Session, datepoll_id: str) -> list[DatepollSubmissionOut]:
    """Per-submission rows for the CSV export, keyed by date id.

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
    comments: dict[str, dict[str, str]] = {sid: {} for sid in sub_ids}
    for r in db.query(DatepollResponse).filter(DatepollResponse.submission_id.in_(sub_ids)).all():
        answers[r.submission_id][r.datepoll_date_id] = r.availability
        if r.comment is not None:
            comments[r.submission_id][r.datepoll_date_id] = r.comment

    return [
        DatepollSubmissionOut(
            submission_id=s.id,
            display_name=s.display_name,
            created_at=s.created_at,
            answers=answers[s.id],
            comments=comments[s.id],
        )
        for s in subs
    ]
