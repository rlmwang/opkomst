"""Chores-feature service helpers.

Mirrors ``services/forms.py`` / ``services/datepolls.py``: ``enrich`` /
``to_out`` / ``to_public_out`` DTO projections and ``apply_chores`` (the
chore diff, matched on chore ``id`` like form questions, ordinals
re-numbered 1..N from input order).

Chapter-scoped lookups live in ``services.access``
(``get_roster_for_user`` / ``roster_scope_filter``).
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Chore, Enrollment, Roster, Shift, ShiftEvent, Volunteer, VolunteerAvailability
from ..schemas.chores import (
    AvailabilityRange,
    CalendarAssigneeOut,
    CalendarDayOut,
    ChoreAccountabilityOut,
    ChoreCalendarOut,
    ChoreOut,
    ChoreVolunteerOut,
    CoverableShiftOut,
    OutlookShiftOut,
    PersonalOutlookOut,
    PersonalPageOut,
    PersonalShiftOut,
    PublicRosterOut,
    RosterListOut,
    RosterOut,
    ScheduleOut,
    ScheduleShiftOut,
    ScheduleStatsOut,
    VolunteerSummaryOut,
)
from . import chore_tick, tenancy
from .chore_assignment import AccountabilityCounts, summarize_accountability
from .events import now_wallclock

# How far past the commit horizon the tentative outlook is projected for
# display. Bounded so the projection is never an infinite list.
OUTLOOK_DAYS = 182

if TYPE_CHECKING:
    from ..schemas.chores import ChoreIn


def get_roster_by_slug_any(db: Session, slug: str) -> Roster | None:
    """Slug lookup excluding archived rosters — used by the public
    route. Returns ``None`` when the slug is unknown OR archived (the
    public surface treats both as "no longer available")."""
    roster = db.query(Roster).filter(Roster.slug == slug).first()
    if roster is None or roster.archived_at is not None:
        return None
    tenancy.bind(roster.tenant_id, roster.tenant.slug)
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
            name_nl=r.name_nl,
            name_en=r.name_en,
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
        name_nl=roster.name_nl,
        name_en=roster.name_en,
        locale=roster.locale,
        chapter_id=roster.chapter_id,
        chapter_name=chapter_name,
        archived=roster.archived_at is not None,
        created_at=roster.created_at,
        period_weeks=roster.period_weeks,
        chore_count=len(chores),
        volunteer_count=volunteer_count,
        description_nl=roster.description_nl,
        description_en=roster.description_en,
        location=roster.location,
        latitude=roster.latitude,
        longitude=roster.longitude,
        image_url=roster.image_url,
        image_artist_instagram=roster.image_artist_instagram,
        starts_on=roster.starts_on,
        ends_on=roster.ends_on,
        reminder_enabled=roster.reminder_enabled,
        reminder_days_before=roster.reminder_days_before,
        commit_horizon_days=roster.commit_horizon_days,
        activated_at=roster.activated_at,
        chores=[ChoreOut.model_validate(c) for c in chores],
    )


def _enrolled_chore_ids(db: Session, volunteer_id: str) -> list[str]:
    return [row[0] for row in db.query(Enrollment.chore_id).filter(Enrollment.volunteer_id == volunteer_id).all()]


def _shift_out(shift: Shift, chore_name: str, *, inherited: bool = False) -> PersonalShiftOut:
    return PersonalShiftOut(
        id=shift.id,
        chore_id=shift.chore_id,
        chore_name=chore_name,
        on_date=shift.on_date,
        status=shift.status,
        inherited=inherited,
    )


def personal_page(db: Session, volunteer: Volunteer) -> PersonalPageOut:
    """The volunteer's personal-page payload: their upcoming assigned
    shifts + the claimable ``open`` shifts on chores they're enrolled in.
    The email is never returned — only ``has_email``."""
    today = now_wallclock().date()
    chore_ids = _enrolled_chore_ids(db, volunteer.id)

    # Upcoming assignments plus the volunteer's finished ones (done/missed),
    # so completed tasks stay visible on their day rather than vanishing the
    # moment they're marked done. The calendar renders each by its status.
    mine = (
        db.query(Shift, Chore.name)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(Shift.volunteer_id == volunteer.id, Shift.status.in_(["scheduled", "done", "missed"]))
        .order_by(Shift.on_date, Shift.id)
        .all()
    )
    # Shifts this volunteer picked up covering for someone who left get an
    # origin note on their page (design §7 disruption provenance).
    inherited_ids = {
        sid
        for (sid,) in db.query(ShiftEvent.shift_id)
        .filter(
            ShiftEvent.volunteer_id == volunteer.id,
            ShiftEvent.kind == "inherited",
            ShiftEvent.shift_id.is_not(None),
        )
        .all()
    }
    open_shifts: list[PersonalShiftOut] = []
    if chore_ids:
        opens = (
            db.query(Shift, Chore.name)
            .join(Chore, Chore.id == Shift.chore_id)
            .filter(Shift.chore_id.in_(chore_ids), Shift.status == "open", Shift.on_date >= today)
            .order_by(Shift.on_date, Shift.id)
            .all()
        )
        open_shifts = [_shift_out(s, name) for s, name in opens]

    coverable: list[CoverableShiftOut] = []
    if chore_ids:
        rows = (
            db.query(Shift, Chore.name, Volunteer.display_name)
            .join(Chore, Chore.id == Shift.chore_id)
            .outerjoin(Volunteer, Volunteer.id == Shift.volunteer_id)
            .filter(
                Shift.chore_id.in_(chore_ids),
                Shift.status == "scheduled",
                Shift.on_date >= today,
                Shift.volunteer_id.is_not(None),
                Shift.volunteer_id != volunteer.id,
            )
            .order_by(Shift.on_date, Shift.id)
            .all()
        )
        coverable = [
            CoverableShiftOut(id=s.id, chore_id=s.chore_id, chore_name=name, on_date=s.on_date, assignee_name=assignee)
            for s, name, assignee in rows
        ]

    availability = [
        AvailabilityRange(start=a.start_date, end=a.end_date)
        for a in db.query(VolunteerAvailability)
        .filter(VolunteerAvailability.volunteer_id == volunteer.id)
        .order_by(VolunteerAvailability.start_date)
        .all()
    ]

    return PersonalPageOut(
        display_name=volunteer.display_name,
        enrolled_chore_ids=chore_ids,
        email_reminders=volunteer.email_reminders,
        has_email=volunteer.encrypted_email is not None,
        link_recovered_at=volunteer.link_recovered_at,
        my_shifts=[_shift_out(s, name, inherited=s.id in inherited_ids) for s, name in mine],
        open_shifts=open_shifts,
        outlook_shifts=_personal_outlook(db, volunteer, today),
        coverable_shifts=coverable,
        availability=availability,
    )


def _personal_outlook(db: Session, volunteer: Volunteer, today: date) -> list[PersonalOutlookOut]:
    """The volunteer's tentative projected turns beyond the commit horizon.
    Empty while the roster is forming."""
    roster = db.query(Roster).filter(Roster.id == volunteer.roster_id).first()
    if roster is None or roster.activated_at is None:
        return []
    window_end = today + timedelta(days=roster.commit_horizon_days)
    if roster.ends_on is not None and roster.ends_on < window_end:
        window_end = roster.ends_on
    outlook_until = today + timedelta(days=OUTLOOK_DAYS)
    if roster.ends_on is not None and roster.ends_on < outlook_until:
        outlook_until = roster.ends_on
    outlook_start = window_end + timedelta(days=1)
    if outlook_start > outlook_until:
        return []
    chores = _chores(db, roster.id)
    chore_names = {c.id: c.name for c in chores}
    proj = chore_tick.project_range(db, roster, chores, outlook_start, outlook_until)
    return sorted(
        (
            PersonalOutlookOut(
                chore_id=pa.occurrence.chore_id,
                chore_name=chore_names.get(pa.occurrence.chore_id, ""),
                on_date=pa.occurrence.on_date,
            )
            for pa in proj
            if pa.volunteer_id == volunteer.id
        ),
        key=lambda o: (o.on_date, o.chore_name),
    )


def _roster_loads(db: Session, roster_id: str) -> dict[str, int]:
    """Per-volunteer load (scheduled + done shifts) across the roster."""
    chore_ids = [row[0] for row in db.query(Chore.id).filter(Chore.roster_id == roster_id).all()]
    if not chore_ids:
        return {}
    rows = (
        db.query(Shift.volunteer_id, func.count(Shift.id))
        .filter(
            Shift.chore_id.in_(chore_ids),
            Shift.volunteer_id.is_not(None),
            Shift.status.in_(["scheduled", "done"]),
        )
        .group_by(Shift.volunteer_id)
        .all()
    )
    return {vid: int(n) for vid, n in rows}


def _accountability(db: Session, roster_id: str) -> dict[str, AccountabilityCounts]:
    """Per-volunteer accountability split, folded from the same
    ``(kind, volunteer_id)`` ShiftEvent stream the favour ledger reads —
    so the ledger and the display provably agree (design §7)."""
    rows = db.query(ShiftEvent.kind, ShiftEvent.volunteer_id).filter(ShiftEvent.roster_id == roster_id).all()
    return summarize_accountability((kind, vid) for kind, vid in rows)


def volunteer_summaries(db: Session, roster: Roster) -> list[VolunteerSummaryOut]:
    """Organiser-facing volunteer list: pseudonym + enrolled chores +
    current load + lifetime accountability counts (from the ShiftEvent
    log). No email/ciphertext/token."""
    volunteers = db.query(Volunteer).filter(Volunteer.roster_id == roster.id).all()
    if not volunteers:
        return []
    vol_ids = [v.id for v in volunteers]
    by_vol: dict[str, list[str]] = {}
    for vid, cid in (
        db.query(Enrollment.volunteer_id, Enrollment.chore_id).filter(Enrollment.volunteer_id.in_(vol_ids)).all()
    ):
        by_vol.setdefault(vid, []).append(cid)
    loads = _roster_loads(db, roster.id)
    counts = _accountability(db, roster.id)
    # A volunteer is "pending" until they hold any shift (pinned or past).
    held = {
        row[0]
        for row in db.query(Shift.volunteer_id)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(Chore.roster_id == roster.id, Shift.volunteer_id.is_not(None))
        .distinct()
    }
    return [
        VolunteerSummaryOut(
            id=v.id,
            display_name=v.display_name,
            enrolled_chore_ids=by_vol.get(v.id, []),
            pending=v.id not in held,
            load=loads.get(v.id, 0),
            regular_turns=(c := counts.get(v.id, AccountabilityCounts())).regular_turns,
            picked_up=c.picked_up,
            completed=c.completed,
            deferred=c.deferred,
            missed=c.missed,
            link_recovered_at=v.link_recovered_at,
        )
        for v in volunteers
    ]


def chore_accountability(db: Session, roster: Roster) -> list[ChoreAccountabilityOut]:
    """Accountability broken down per chore: for each chore (by ordinal), the
    volunteers enrolled in it with their per-chore turn split, folded from
    the ShiftEvent stream joined to each event's shift (so an event counts
    only against the chore whose shift it was). A volunteer with no held
    shift of the chore yet is flagged ``pending``."""
    chores = _chores(db, roster.id)
    if not chores:
        return []
    vols = {v.id: v for v in db.query(Volunteer).filter(Volunteer.roster_id == roster.id)}

    enrolled: dict[str, list[str]] = {}
    if vols:
        for cid, vid in (
            db.query(Enrollment.chore_id, Enrollment.volunteer_id)
            .filter(Enrollment.volunteer_id.in_(list(vols.keys())))
            .all()
        ):
            enrolled.setdefault(cid, []).append(vid)

    # ShiftEvent stream grouped by the chore its shift belongs to. The inner
    # join drops events whose shift was deleted (``shift_id`` SET NULL) —
    # they can't be attributed to a chore.
    events_by_chore: dict[str, list[tuple[str, str]]] = {}
    for cid, kind, vid in (
        db.query(Shift.chore_id, ShiftEvent.kind, ShiftEvent.volunteer_id)
        .join(Shift, Shift.id == ShiftEvent.shift_id)
        .filter(ShiftEvent.roster_id == roster.id)
        .all()
    ):
        events_by_chore.setdefault(cid, []).append((kind, vid))

    held = {
        (cid, vid)
        for cid, vid in db.query(Shift.chore_id, Shift.volunteer_id)
        .filter(Shift.chore_id.in_([c.id for c in chores]), Shift.volunteer_id.is_not(None))
        .distinct()
    }

    out: list[ChoreAccountabilityOut] = []
    for chore in chores:
        counts = summarize_accountability(events_by_chore.get(chore.id, []))
        rows: list[ChoreVolunteerOut] = []
        for vid in enrolled.get(chore.id, []):
            v = vols.get(vid)
            if v is None:
                continue
            c = counts.get(vid, AccountabilityCounts())
            rows.append(
                ChoreVolunteerOut(
                    id=v.id,
                    display_name=v.display_name,
                    pending=(chore.id, v.id) not in held,
                    regular_turns=c.regular_turns,
                    picked_up=c.picked_up,
                    completed=c.completed,
                    deferred=c.deferred,
                    missed=c.missed,
                )
            )
        # Busiest first (own + picked-up turns), then pseudonym for stability.
        rows.sort(key=lambda r: (-(r.regular_turns + r.picked_up), (r.display_name or "").lower()))
        out.append(ChoreAccountabilityOut(chore_id=chore.id, chore_name=chore.name, emoji=chore.emoji, volunteers=rows))
    return out


def parse_month(month: str | None, today: date) -> tuple[int, int]:
    """Parse a ``YYYY-MM`` query param into (year, month), falling back to the
    current month on absence or malformed input. Shared by the organiser and
    public-token calendar endpoints."""
    if month:
        try:
            year, mon = (int(x) for x in month.split("-", 1))
        except ValueError:
            return today.year, today.month
        if 1 <= mon <= 12:
            return year, mon
    return today.year, today.month


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start, end


def chore_calendar(db: Session, roster: Roster, year: int, month: int, today: date) -> list[ChoreCalendarOut]:
    """One month of occurrences per chore (ordered by ordinal). Days on/before
    the commit horizon come from the actual ``Shift`` rows (past history + the
    pinned window — real rows, so a since-changed pattern doesn't rewrite the
    past); days beyond it come from the projection and are ``tentative``. A day
    carries one assignee entry per slot (``people_per_shift``)."""
    chores = _chores(db, roster.id)
    if not chores:
        return []
    chore_ids = [c.id for c in chores]
    m_start, m_end = _month_bounds(year, month)
    horizon_end = chore_tick.horizon_end(roster, today)
    vol_names = {v.id: v.display_name for v in db.query(Volunteer).filter(Volunteer.roster_id == roster.id)}

    actual: dict[tuple[str, date], list[CalendarAssigneeOut]] = {}
    real_end = min(m_end, horizon_end)
    if m_start <= real_end:
        rows = (
            db.query(Shift, Volunteer.display_name)
            .outerjoin(Volunteer, Volunteer.id == Shift.volunteer_id)
            .filter(Shift.chore_id.in_(chore_ids), Shift.on_date >= m_start, Shift.on_date <= real_end)
            .order_by(Shift.on_date, Shift.slot_index)
            .all()
        )
        for s, name in rows:
            actual.setdefault((s.chore_id, s.on_date), []).append(
                CalendarAssigneeOut(name=name, open=s.volunteer_id is None, status=s.status, shift_id=s.id)
            )

    projected: dict[tuple[str, date], list[CalendarAssigneeOut]] = {}
    proj_start = max(m_start, horizon_end + timedelta(days=1))
    proj_end = min(m_end, today + timedelta(days=OUTLOOK_DAYS))
    if roster.ends_on is not None and roster.ends_on < proj_end:
        proj_end = roster.ends_on
    if roster.activated_at is not None and proj_start <= proj_end:
        for pa in chore_tick.project_range(db, roster, chores, proj_start, proj_end):
            projected.setdefault((pa.occurrence.chore_id, pa.occurrence.on_date), []).append(
                CalendarAssigneeOut(
                    name=vol_names.get(pa.volunteer_id) if pa.volunteer_id else None,
                    open=pa.volunteer_id is None,
                    status="scheduled",
                )
            )

    out: list[ChoreCalendarOut] = []
    for c in chores:
        dates = sorted({d for (cid, d) in actual if cid == c.id} | {d for (cid, d) in projected if cid == c.id})
        days = [
            CalendarDayOut(
                on_date=d,
                tentative=d > horizon_end,
                assignees=(projected if d > horizon_end else actual).get((c.id, d), []),
            )
            for d in dates
        ]
        out.append(ChoreCalendarOut(chore_id=c.id, chore_name=c.name, emoji=c.emoji, days=days))
    return out


def _day_signature(day: CalendarDayOut) -> tuple:
    """Identity of a day's assignment, for diffing before/after a rebalance."""
    return tuple(sorted((a.open, a.name or "") for a in day.assignees))


def rebalance_preview_calendar(
    db: Session, roster: Roster, year: int, month: int, today: date
) -> list[ChoreCalendarOut]:
    """The month calendar as it would look after a "fold in now" rebalance,
    with ``changed`` flagged on days whose assignment differs from now. Runs
    the rebalance core in a SAVEPOINT and rolls it back — nothing persists."""
    before = {
        (cal.chore_id, d.on_date): _day_signature(d)
        for cal in chore_calendar(db, roster, year, month, today)
        for d in cal.days
    }
    savepoint = db.begin_nested()
    try:
        chore_tick.rebalance_core(db, roster, today)
        db.flush()
        after = chore_calendar(db, roster, year, month, today)
    finally:
        savepoint.rollback()
    for cal in after:
        for day in cal.days:
            if before.get((cal.chore_id, day.on_date)) != _day_signature(day):
                day.changed = True
    return after


def schedule(db: Session, roster: Roster) -> ScheduleOut:
    """Organiser schedule: lifetime status counts, the pinned **confirmed**
    window (materialised rows, today onward), and the projected **outlook**
    beyond the commit horizon (computed on demand, date-bounded)."""
    chores = _chores(db, roster.id)
    chore_ids = [c.id for c in chores]
    empty_stats = ScheduleStatsOut(scheduled=0, done=0, missed=0, open=0)
    if not chore_ids:
        return ScheduleOut(stats=empty_stats, confirmed=[], outlook=[], outlook_until=None)

    counts = {
        status: int(n)
        for status, n in db.query(Shift.status, func.count(Shift.id))
        .filter(Shift.chore_id.in_(chore_ids))
        .group_by(Shift.status)
        .all()
    }
    today = now_wallclock().date()
    rows = (
        db.query(Shift, Chore.name, Volunteer.display_name)
        .join(Chore, Chore.id == Shift.chore_id)
        .outerjoin(Volunteer, Volunteer.id == Shift.volunteer_id)
        .filter(Shift.chore_id.in_(chore_ids), Shift.on_date >= today)
        .order_by(Shift.on_date, Chore.ordinal, Shift.slot_index)
        .all()
    )
    confirmed = [
        ScheduleShiftOut(
            id=s.id,
            chore_id=s.chore_id,
            chore_name=chore_name,
            on_date=s.on_date,
            slot_index=s.slot_index,
            status=s.status,
            assignee_name=assignee_name,
        )
        for s, chore_name, assignee_name in rows
    ]

    # Outlook: projected assignments beyond the pinned window, up to a
    # bounded horizon. Only meaningful once the roster is running.
    outlook: list[OutlookShiftOut] = []
    outlook_until: date | None = None
    if roster.activated_at is not None:
        window_end = today + timedelta(days=roster.commit_horizon_days)
        if roster.ends_on is not None and roster.ends_on < window_end:
            window_end = roster.ends_on
        outlook_until = today + timedelta(days=OUTLOOK_DAYS)
        if roster.ends_on is not None and roster.ends_on < outlook_until:
            outlook_until = roster.ends_on
        outlook_start = window_end + timedelta(days=1)
        if outlook_start <= outlook_until:
            chore_names = {c.id: c.name for c in chores}
            vol_names = {
                v.id: v.display_name for v in db.query(Volunteer).filter(Volunteer.roster_id == roster.id).all()
            }
            proj = chore_tick.project_range(db, roster, chores, outlook_start, outlook_until)
            outlook = sorted(
                (
                    OutlookShiftOut(
                        chore_id=pa.occurrence.chore_id,
                        chore_name=chore_names.get(pa.occurrence.chore_id, ""),
                        on_date=pa.occurrence.on_date,
                        assignee_name=vol_names.get(pa.volunteer_id) if pa.volunteer_id else None,
                    )
                    for pa in proj
                ),
                key=lambda o: (o.on_date, o.chore_name),
            )

    return ScheduleOut(
        stats=ScheduleStatsOut(
            scheduled=counts.get("scheduled", 0),
            done=counts.get("done", 0),
            missed=counts.get("missed", 0),
            open=counts.get("open", 0),
        ),
        confirmed=confirmed,
        outlook=outlook,
        outlook_until=outlook_until,
    )


def to_public_out(db: Session, roster: Roster) -> PublicRosterOut:
    """Public by-slug DTO: name + recurrence + chores, nothing internal."""
    return PublicRosterOut(
        id=roster.id,
        name_nl=roster.name_nl,
        name_en=roster.name_en,
        description_nl=roster.description_nl,
        description_en=roster.description_en,
        location=roster.location,
        latitude=roster.latitude,
        longitude=roster.longitude,
        image_url=roster.image_url,
        image_artist_instagram=roster.image_artist_instagram,
        locale=roster.locale,
        period_weeks=roster.period_weeks,
        starts_on=roster.starts_on,
        ends_on=roster.ends_on,
        chores=[ChoreOut.model_validate(c) for c in _chores(db, roster.id)],
    )
