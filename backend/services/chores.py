"""Chores-feature service helpers.

Mirrors ``services/forms.py`` / ``services/datepolls.py``: ``enrich`` /
``to_out`` / ``to_public_out`` DTO projections and ``apply_chores`` (the
chore diff, matched on chore ``id`` like form questions, ordinals
re-numbered 1..N from input order).

Chapter-scoped lookups live in ``services.access``
(``get_roster_for_user`` / ``roster_scope_filter``).
"""

from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Chore, Enrollment, Roster, Volunteer
from ..schemas.chores import (
    ChoreOut,
    PersonalPageOut,
    PublicRosterOut,
    RosterListOut,
    RosterOut,
    VolunteerSummaryOut,
)

if TYPE_CHECKING:
    from ..schemas.chores import ChoreIn


def get_roster_by_slug_any(db: Session, slug: str) -> Roster | None:
    """Slug lookup excluding archived rosters — used by the public
    route. Returns ``None`` when the slug is unknown OR archived (the
    public surface treats both as "no longer available")."""
    roster = db.query(Roster).filter(Roster.slug == slug).first()
    if roster is None or roster.archived_at is not None:
        return None
    return roster


def apply_chores(db: Session, roster_id: str, chores: list["ChoreIn"]) -> None:
    """Diff-apply the chore payload against the roster's current rows.
    Matches by id: rows with no id (or an unknown id) insert; matching
    ids update in place; rows absent from the payload are deleted (the FK
    cascade takes their shifts/enrollments). Ordinals are re-numbered
    1..N from input order. ``cycle_slots`` are already normalised by the
    schema validator. Caller commits."""
    existing = {c.id: c for c in db.query(Chore).filter(Chore.roster_id == roster_id).all()}
    seen_ids: set[str] = set()
    for ordinal, payload in enumerate(chores, start=1):
        if payload.id and payload.id in existing:
            row = existing[payload.id]
            row.ordinal = ordinal
            row.name = payload.name
            row.description = payload.description
            row.cycle_slots = payload.cycle_slots
            row.people_per_shift = payload.people_per_shift
            row.emoji = payload.emoji
            seen_ids.add(payload.id)
        else:
            db.add(
                Chore(
                    roster_id=roster_id,
                    ordinal=ordinal,
                    name=payload.name,
                    description=payload.description,
                    cycle_slots=payload.cycle_slots,
                    people_per_shift=payload.people_per_shift,
                    emoji=payload.emoji,
                )
            )

    for cid, row in existing.items():
        if cid not in seen_ids:
            db.delete(row)
    db.flush()


# --- DTO projections -------------------------------------------------


def _chapter_names(db: Session, chapter_ids: set[str]) -> dict[str, str]:
    if not chapter_ids:
        return {}
    rows = db.query(Chapter.id, Chapter.name).filter(Chapter.id.in_(chapter_ids), Chapter.deleted_at.is_(None)).all()
    return {cid: name for cid, name in rows}


def _counts(db: Session, roster_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Per-roster (chore_count, volunteer_count) via two grouped queries."""
    chores = {
        rid: int(n)
        for rid, n in db.query(Chore.roster_id, func.count(Chore.id))
        .filter(Chore.roster_id.in_(roster_ids))
        .group_by(Chore.roster_id)
        .all()
    }
    volunteers = {
        rid: int(n)
        for rid, n in db.query(Volunteer.roster_id, func.count(Volunteer.id))
        .filter(Volunteer.roster_id.in_(roster_ids))
        .group_by(Volunteer.roster_id)
        .all()
    }
    return chores, volunteers


def enrich(db: Session, rosters: list[Roster]) -> list[RosterListOut]:
    """Build ``RosterListOut`` rows with batched lookups: one query for
    chapter names, two grouped count queries. No N+1."""
    if not rosters:
        return []
    names = _chapter_names(db, {r.chapter_id for r in rosters if r.chapter_id})
    ids = [r.id for r in rosters]
    chore_counts, vol_counts = _counts(db, ids)
    return [
        RosterListOut(
            id=r.id,
            slug=r.slug,
            name=r.name,
            locale=r.locale,
            chapter_id=r.chapter_id,
            chapter_name=names.get(r.chapter_id) if r.chapter_id else None,
            archived=r.archived_at is not None,
            created_at=r.created_at,
            period_weeks=r.period_weeks,
            chore_count=chore_counts.get(r.id, 0),
            volunteer_count=vol_counts.get(r.id, 0),
        )
        for r in rosters
    ]


def _chores(db: Session, roster_id: str) -> list[Chore]:
    return db.query(Chore).filter(Chore.roster_id == roster_id).order_by(Chore.ordinal).all()


def to_out(db: Session, roster: Roster) -> RosterOut:
    """Single-roster organiser DTO: list fields + recurrence config +
    the full chore list. One chapter lookup + one chore query + one
    volunteer count."""
    chapter_name = _chapter_names(db, {roster.chapter_id}).get(roster.chapter_id) if roster.chapter_id else None
    chores = _chores(db, roster.id)
    volunteer_count = db.query(func.count(Volunteer.id)).filter(Volunteer.roster_id == roster.id).scalar() or 0
    return RosterOut(
        id=roster.id,
        slug=roster.slug,
        name=roster.name,
        locale=roster.locale,
        chapter_id=roster.chapter_id,
        chapter_name=chapter_name,
        archived=roster.archived_at is not None,
        created_at=roster.created_at,
        period_weeks=roster.period_weeks,
        chore_count=len(chores),
        volunteer_count=volunteer_count,
        description=roster.description,
        location=roster.location,
        latitude=roster.latitude,
        longitude=roster.longitude,
        image_url=roster.image_url,
        image_artist_instagram=roster.image_artist_instagram,
        anchor_monday=roster.anchor_monday,
        starts_on=roster.starts_on,
        ends_on=roster.ends_on,
        reminder_enabled=roster.reminder_enabled,
        reminder_days_before=roster.reminder_days_before,
        chores=[ChoreOut.model_validate(c) for c in chores],
    )


def _enrolled_chore_ids(db: Session, volunteer_id: str) -> list[str]:
    return [row[0] for row in db.query(Enrollment.chore_id).filter(Enrollment.volunteer_id == volunteer_id).all()]


def personal_page(db: Session, volunteer: Volunteer) -> PersonalPageOut:
    """The volunteer's personal-page payload. ``my_shifts`` /
    ``open_shifts`` are empty until shift generation (task 06). The email
    is never returned — only ``has_email`` (whether a ciphertext is on
    file)."""
    return PersonalPageOut(
        display_name=volunteer.display_name,
        enrolled_chore_ids=_enrolled_chore_ids(db, volunteer.id),
        email_reminders=volunteer.email_reminders,
        has_email=volunteer.encrypted_email is not None,
        my_shifts=[],
        open_shifts=[],
    )


def volunteer_summaries(db: Session, roster: Roster) -> list[VolunteerSummaryOut]:
    """Organiser-facing volunteer list: pseudonym + enrolled chores +
    load (0 until shifts exist — task 06). No email/ciphertext/token."""
    volunteers = db.query(Volunteer).filter(Volunteer.roster_id == roster.id).all()
    if not volunteers:
        return []
    vol_ids = [v.id for v in volunteers]
    by_vol: dict[str, list[str]] = {}
    for vid, cid in (
        db.query(Enrollment.volunteer_id, Enrollment.chore_id).filter(Enrollment.volunteer_id.in_(vol_ids)).all()
    ):
        by_vol.setdefault(vid, []).append(cid)
    return [
        VolunteerSummaryOut(
            id=v.id,
            display_name=v.display_name,
            enrolled_chore_ids=by_vol.get(v.id, []),
            load=0,
        )
        for v in volunteers
    ]


def to_public_out(db: Session, roster: Roster) -> PublicRosterOut:
    """Public by-slug DTO: name + recurrence + chores, nothing internal."""
    return PublicRosterOut(
        id=roster.id,
        name=roster.name,
        description=roster.description,
        location=roster.location,
        latitude=roster.latitude,
        longitude=roster.longitude,
        image_url=roster.image_url,
        image_artist_instagram=roster.image_artist_instagram,
        locale=roster.locale,
        period_weeks=roster.period_weeks,
        anchor_monday=roster.anchor_monday,
        starts_on=roster.starts_on,
        ends_on=roster.ends_on,
        chores=[ChoreOut.model_validate(c) for c in _chores(db, roster.id)],
    )
