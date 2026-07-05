"""Chapter-scoped chore-roster CRUD + organiser-side reads.

Mirrors the events/forms/datepolls router shape: create, list active,
list archived, get, update, archive, restore, delete-when-archived,
image. All require an approved user; all are scoped to the user's
chapter via ``access.get_roster_for_user`` (single) or
``access.list_filter`` (lists). Archive/restore/delete go through the
shared ``services.crud`` helper.

Public-by-slug surfaces live in ``routers/chores_public.py`` (task 05);
the schedule / volunteers reads arrive with the data (task 06).
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..config import settings
from ..database import get_db
from ..models import Chore, Enrollment, Roster, Shift, User, Volunteer
from ..schemas.chores import (
    ChoreAccountabilityOut,
    ChoreCalendarOut,
    RosterCreate,
    RosterListOut,
    RosterOut,
    RosterUpdate,
    ScheduleOut,
    ShiftReassignIn,
    VolunteerSummaryOut,
)
from ..schemas.common import EditLinkRecoverOut
from ..services import access, chore_tick, crud, edit_token
from ..services import chores as chores_svc
from ..services import image as image_svc
from ..services.events import now_wallclock
from ..services.rate_limit import Limits, limiter
from ..services.slug import new_slug

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/chores", tags=["chores"])


@router.post("", response_model=RosterOut, status_code=201)
@limiter.limit(Limits.ORG_RARE)
def create_roster(
    request: Request,
    data: RosterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    """Create a roster. Chores are optional at create — a blank roster
    can be saved and chores added on the edit page. The caller-supplied
    ``chapter_id`` must be in the user's set."""
    access.assert_user_can_assign_chapter(db, user, data.chapter_id)
    roster = Roster(
        slug=new_slug(),
        name=data.name,
        description=data.description,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        image_artist_instagram=data.image_artist_instagram,
        locale=data.locale,
        period_weeks=data.period_weeks,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        reminder_enabled=data.reminder_enabled,
        reminder_days_before=data.reminder_days_before,
        commit_horizon_days=data.commit_horizon_days,
        chapter_id=data.chapter_id,
        created_by=user.id,
    )
    db.add(roster)
    db.flush()  # Need roster.id for the chore rows below.
    if data.chores:
        chores_svc.apply_chores(db, roster.id, data.chores)
    db.commit()
    db.refresh(roster)
    logger.info("roster_created", roster_id=roster.id, actor_id=user.id, chapter_id=data.chapter_id)
    return chores_svc.to_out(db, roster)


@router.get("", response_model=list[RosterListOut])
def list_rosters(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[RosterListOut]:
    rows = (
        db.query(Roster)
        .filter(access.list_filter(db, user, Roster.chapter_id, chapter_id), Roster.archived_at.is_(None))
        .order_by(Roster.created_at.desc())
        .all()
    )
    return chores_svc.enrich(db, rows)


@router.get("/archived", response_model=list[RosterListOut])
def list_archived_rosters(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[RosterListOut]:
    rows = (
        db.query(Roster)
        .filter(access.list_filter(db, user, Roster.chapter_id, chapter_id), Roster.archived_at.is_not(None))
        .order_by(Roster.archived_at.desc())
        .all()
    )
    return chores_svc.enrich(db, rows)


@router.get("/{roster_id}", response_model=RosterOut)
def get_roster(
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    roster = access.get_roster_for_user(db, roster_id, user)
    return chores_svc.to_out(db, roster)


@router.get("/{roster_id}/volunteers", response_model=list[VolunteerSummaryOut])
def list_volunteers(
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[VolunteerSummaryOut]:
    """Volunteers on a roster: pseudonym + enrolled chores + load.
    Never the email/ciphertext/token (privacy — see the leak-guard
    test). ``load`` is 0 until shift generation (task 06)."""
    roster = access.get_roster_for_user(db, roster_id, user)
    return chores_svc.volunteer_summaries(db, roster)


@router.post("/{roster_id}/volunteers/{volunteer_id}/edit-link", response_model=EditLinkRecoverOut)
@limiter.limit(Limits.ORG_WRITE)
def recover_volunteer_edit_link(
    request: Request,
    roster_id: str,
    volunteer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EditLinkRecoverOut:
    """Organiser recovery of a volunteer's lost personal-page link —
    rotates the token (never reveals it) and permanently stamps
    ``link_recovered_at``; see ``services/edit_token.recover``."""
    roster = access.get_roster_for_user(db, roster_id, user)
    volunteer = db.query(Volunteer).filter(Volunteer.id == volunteer_id, Volunteer.roster_id == roster.id).first()
    if volunteer is None:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    raw = edit_token.recover(volunteer)
    db.commit()
    logger.info("volunteer_edit_link_recovered", roster_id=roster.id, volunteer_id=volunteer_id, actor_id=user.id)
    return EditLinkRecoverOut(edit_token=raw)


@router.get("/{roster_id}/accountability", response_model=list[ChoreAccountabilityOut])
def chore_accountability(
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[ChoreAccountabilityOut]:
    """Accountability broken down per chore: one section per chore (by
    ordinal), each listing the enrolled volunteers with their per-chore
    turn split. Never the email/ciphertext/token."""
    roster = access.get_roster_for_user(db, roster_id, user)
    return chores_svc.chore_accountability(db, roster)


@router.get("/{roster_id}/schedule", response_model=ScheduleOut)
def get_schedule(
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> ScheduleOut:
    """Upcoming shifts (today onward) with the assignee pseudonym, plus
    lifetime done/missed/scheduled/open counts."""
    roster = access.get_roster_for_user(db, roster_id, user)
    return chores_svc.schedule(db, roster)


@router.post("/{roster_id}/activate", response_model=RosterOut)
@limiter.limit(Limits.ORG_RARE)
def activate_roster(
    request: Request,
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    """Start a forming roster: flip it to running and pin the commit
    horizon now. One-way — 409 if already running (design §7 bootstrap)."""
    roster = access.get_roster_for_user(db, roster_id, user)
    if roster.activated_at is not None:
        raise HTTPException(status_code=409, detail="Roster already started")
    roster.activated_at = datetime.now(UTC)
    db.flush()
    chore_tick.pin_roster(db, roster, now_wallclock().date())
    logger.info("roster_activated", roster_id=roster.id, actor_id=user.id)
    return chores_svc.to_out(db, roster)


@router.post("/{roster_id}/rebalance", response_model=RosterOut)
@limiter.limit(Limits.ORG_RARE)
def rebalance_roster(
    request: Request,
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    """Re-pin the current commit window from the fresh projection, folding
    pending volunteers in now. Drops un-acted pins and reassigns them, so
    it changes confirmed shifts — an explicit, opt-in organiser action."""
    roster = access.get_roster_for_user(db, roster_id, user)
    if roster.activated_at is None:
        raise HTTPException(status_code=409, detail="Roster is not running")
    chore_tick.rebalance_roster(db, roster, now_wallclock().date())
    logger.info("roster_rebalanced", roster_id=roster.id, actor_id=user.id)
    return chores_svc.to_out(db, roster)


@router.post("/{roster_id}/shifts/{shift_id}/reassign", status_code=204)
@limiter.limit(Limits.ORG_WRITE)
def reassign_shift(
    request: Request,
    roster_id: str,
    shift_id: str,
    data: ShiftReassignIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Hand a pinned shift to a chosen volunteer — the organiser-side
    "overnemen" on the roster calendar. Mirrors the public claim/cover
    semantics: taking an open shift records ``claimed``, taking over
    another's confirmed shift records ``covered`` (+1 favour credit either
    way). The past is frozen and done/missed shifts can't change hands;
    the new assignee must be enrolled in the shift's chore."""
    roster = access.get_roster_for_user(db, roster_id, user)
    shift = (
        db.query(Shift)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(Shift.id == shift_id, Chore.roster_id == roster.id)
        .first()
    )
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    if shift.on_date < now_wallclock().date() or shift.status not in ("scheduled", "open"):
        raise HTTPException(status_code=409, detail="This shift can no longer change hands")
    volunteer = db.query(Volunteer).filter(Volunteer.id == data.volunteer_id, Volunteer.roster_id == roster.id).first()
    enrolled = volunteer is not None and (
        db.query(Enrollment)
        .filter(Enrollment.volunteer_id == volunteer.id, Enrollment.chore_id == shift.chore_id)
        .first()
        is not None
    )
    if volunteer is None or not enrolled:
        raise HTTPException(status_code=409, detail="That volunteer isn't enrolled in this chore")
    if shift.volunteer_id == volunteer.id:
        return  # already theirs — nothing to change
    kind = "covered" if shift.volunteer_id is not None else "claimed"
    chore_tick.record_event(db, roster_id=roster.id, volunteer_id=volunteer.id, kind=kind, shift_id=shift.id)
    shift.volunteer_id = volunteer.id
    shift.status = "scheduled"
    shift.reminder_sent_at = None
    db.commit()
    logger.info("shift_reassigned", roster_id=roster.id, actor_id=user.id)


@router.get("/{roster_id}/calendar", response_model=list[ChoreCalendarOut])
def chore_calendar(
    roster_id: str,
    month: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[ChoreCalendarOut]:
    """One month of the roster as a per-chore calendar. ``month`` is
    ``YYYY-MM`` (defaults to the current month). Past days come from the
    shift log, the horizon window from the pins, beyond it from the
    projection (flagged ``tentative``)."""
    roster = access.get_roster_for_user(db, roster_id, user)
    today = now_wallclock().date()
    year, mon = chores_svc.parse_month(month, today)
    return chores_svc.chore_calendar(db, roster, year, mon, today)


@router.get("/{roster_id}/rebalance/preview", response_model=list[ChoreCalendarOut])
def rebalance_preview(
    roster_id: str,
    month: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[ChoreCalendarOut]:
    """The month calendar as it would look after a "fold in now" rebalance,
    with changed days flagged — without persisting anything (dry-run rolled
    back in a savepoint). Feeds the fold-in confirmation dialog."""
    roster = access.get_roster_for_user(db, roster_id, user)
    if roster.activated_at is None:
        raise HTTPException(status_code=409, detail="Roster is not running")
    today = now_wallclock().date()
    year, mon = chores_svc.parse_month(month, today)
    return chores_svc.rebalance_preview_calendar(db, roster, year, mon, today)


@router.put("/{roster_id}", response_model=RosterOut)
@limiter.limit(Limits.ORG_WRITE)
def update_roster(
    request: Request,
    roster_id: str,
    data: RosterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    """Update a roster. Chapter changes are allowed but the new one must
    be in the user's set. Chores are diff-applied on id; shrinking
    ``period_weeks`` clamps now-out-of-range ``cycle_slots`` (the schema
    validator handles the clamp)."""
    roster = access.get_roster_for_user(db, roster_id, user)
    if data.chapter_id != roster.chapter_id:
        access.assert_user_can_assign_chapter(db, user, data.chapter_id)

    roster.name = data.name
    roster.description = data.description
    roster.location = data.location
    roster.latitude = data.latitude
    roster.longitude = data.longitude
    roster.image_artist_instagram = data.image_artist_instagram
    roster.chapter_id = data.chapter_id
    roster.locale = data.locale
    roster.period_weeks = data.period_weeks
    roster.starts_on = data.starts_on
    roster.ends_on = data.ends_on
    roster.reminder_enabled = data.reminder_enabled
    roster.reminder_days_before = data.reminder_days_before
    roster.commit_horizon_days = data.commit_horizon_days
    chores_svc.apply_chores(db, roster.id, data.chores)
    db.commit()
    db.refresh(roster)
    logger.info("roster_updated", roster_id=roster.id, actor_id=user.id)
    return chores_svc.to_out(db, roster)


@router.post("/{roster_id}/archive", response_model=RosterOut)
@limiter.limit(Limits.ORG_RARE)
def archive_roster(
    request: Request,
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    roster = access.get_roster_for_user(db, roster_id, user)
    crud.archive(db, roster, log_event="roster_archived", actor_id=user.id)
    return chores_svc.to_out(db, roster)


@router.post("/{roster_id}/restore", response_model=RosterOut)
@limiter.limit(Limits.ORG_RARE)
def restore_roster(
    request: Request,
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    roster = access.get_roster_for_user(db, roster_id, user)
    crud.restore(db, roster, log_event="roster_restored", actor_id=user.id)
    return chores_svc.to_out(db, roster)


@router.delete("/{roster_id}", status_code=204)
@limiter.limit(Limits.ORG_RARE)
def delete_roster(
    request: Request,
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Hard-delete an archived roster. Refuses unless archived first —
    deleting a live roster with volunteers/shifts would be a data-loss
    footgun. Cascades through chores / volunteers / enrollments / shifts
    via the FK ON DELETE CASCADEs."""
    roster = access.get_roster_for_user(db, roster_id, user)
    crud.hard_delete(
        db,
        roster,
        log_event="roster_deleted",
        actor_id=user.id,
        conflict_detail="Archive the roster before deleting it",
    )


@router.post("/{roster_id}/image", response_model=RosterOut)
@limiter.limit(Limits.ORG_RARE)
async def upload_roster_image(
    request: Request,
    roster_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    """Upload (or replace) the roster's hero image — same 4:5 GitHub
    pipeline as the other entities (``services/image.py``)."""
    if not settings.event_images_enabled:
        raise HTTPException(status_code=503, detail="Image storage is not configured")
    roster = access.get_roster_for_user(db, roster_id, user)
    raw = await file.read()
    timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
    try:
        roster.image_url = image_svc.replace_entity_image(
            folder="chores", entity_id=roster.id, raw=raw, timestamp_ms=timestamp_ms
        )
    except image_svc.ImageProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except image_svc.GithubUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    db.refresh(roster)
    logger.info("roster_image_uploaded", roster_id=roster.id, actor_id=user.id)
    return chores_svc.to_out(db, roster)


@router.delete("/{roster_id}/image", response_model=RosterOut)
@limiter.limit(Limits.ORG_RARE)
def delete_roster_image(
    request: Request,
    roster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> RosterOut:
    """Clear the image reference. The file in the repo is left alone."""
    roster = access.get_roster_for_user(db, roster_id, user)
    if roster.image_url is None:
        raise HTTPException(status_code=404, detail="No image to delete")
    roster.image_url = None
    db.commit()
    db.refresh(roster)
    logger.info("roster_image_deleted", roster_id=roster.id, actor_id=user.id)
    return chores_svc.to_out(db, roster)
