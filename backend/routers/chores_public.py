"""Public-by-slug + by-token surfaces for one chore roster.

All keyed by the public slug or a volunteer's secret edit-token, all
unauthenticated. Split from the organiser router for the same reason
``events_public`` / ``forms_public`` / ``datepolls_public`` exist: zero
shared auth/scope code with the chapter-scoped CRUD.

* ``GET  /by-slug/{slug}`` — the JSON the public enrol page reads.
* ``GET  /by-slug/{slug}/qr.svg`` — QR resolving to ``/c/{slug}``.
* ``POST /by-slug/{slug}/enroll`` — public enrolment; returns the secret
  personal-page token once.
* ``GET  /by-token/{token}`` — the volunteer's personal page.
* ``PUT  /by-token/{token}`` — edit enrolment (chores, name, reminders).
* ``POST /by-token/{token}/leave`` — remove the volunteer (email gone).
* ``POST /by-token/{token}/shifts/{id}/done`` — assignee marks it done.
* ``POST /by-token/{token}/shifts/{id}/handoff`` — give it up; it reopens
  and is re-assigned to someone else.
* ``POST /by-token/{token}/shifts/{id}/claim`` — take an open shift.

The email contract (§6): an address is used once (plaintext, transient)
to send the welcome link, and retained (encrypted) only while the
volunteer wants reminders. ``email_reminders`` off ⇒ ``encrypted_email``
is NULL — enforced on every write here.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Chore, Enrollment, Roster, Shift, Volunteer
from ..schemas.chores import (
    EnrollAck,
    EnrollEditIn,
    EnrollIn,
    PersonalPageOut,
    PublicRosterOut,
)
from ..services import chore_tick, edit_token, encryption, mail, public_access
from ..services import chores as chores_svc
from ..services.qr import render_qr
from ..services.rate_limit import Limits, limiter

PUBLIC_BASE_URL = str(settings.public_base_url).rstrip("/")
_GONE = "This roster is no longer available."

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/chores", tags=["chores"])


def _volunteer_by_token(db: Session, token: str) -> Volunteer:
    return public_access.resolve_by_token(
        db,
        Volunteer,
        token,
        parent_model=Roster,
        parent_fk=Volunteer.roster_id,
        gone_detail=_GONE,
    )


def _validate_chore_ids(db: Session, roster_id: str, chore_ids: list[str]) -> None:
    valid = {row[0] for row in db.query(Chore.id).filter(Chore.roster_id == roster_id).all()}
    for cid in chore_ids:
        if cid not in valid:
            raise HTTPException(status_code=400, detail="Unknown chore_id")


@router.get("/by-slug/{slug}/qr.svg")
def get_roster_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    """QR SVG for one slug. Resolves the roster first so a typo'd slug
    410s rather than 200ing with a wrong-target QR."""
    roster = public_access.resolve_by_slug(db, Roster, slug, gone_detail=_GONE)
    return Response(
        content=render_qr(f"{PUBLIC_BASE_URL}/c/{roster.slug}"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/by-slug/{slug}", response_model=PublicRosterOut)
def get_public_roster(slug: str, db: Session = Depends(get_db)) -> PublicRosterOut:
    return chores_svc.to_public_out(db, public_access.resolve_by_slug(db, Roster, slug, gone_detail=_GONE))


@router.post("/by-slug/{slug}/enroll", response_model=EnrollAck)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def enroll(
    request: Request,
    slug: str,
    data: EnrollIn,
    db: Session = Depends(get_db),
) -> EnrollAck:
    roster = public_access.resolve_by_slug(db, Roster, slug, gone_detail=_GONE)
    _validate_chore_ids(db, roster.id, data.chore_ids)

    raw, token_hash = edit_token.new_edit_token()
    email = data.email
    # Retain the address only if the volunteer wants reminders; otherwise
    # it's used once for the welcome link and never stored (§6).
    retain = email is not None and data.email_reminders
    volunteer = Volunteer(
        roster_id=roster.id,
        display_name=data.display_name,
        email_reminders=retain,
        encrypted_email=encryption.encrypt(email) if (retain and email is not None) else None,
        edit_token_hash=token_hash,
    )
    db.add(volunteer)
    db.flush()  # need volunteer.id for the enrolment rows
    for cid in dict.fromkeys(data.chore_ids):
        db.add(Enrollment(volunteer_id=volunteer.id, chore_id=cid))
    db.commit()

    if email is not None:
        # Plaintext, at request time, fire-and-forget — no decrypt.
        mail.send_email(
            to=email,
            template_name="chore_welcome.html",
            context={"personal_url": mail.build_url(f"c/{slug}", s=raw)},
            locale=roster.locale,
        )
    logger.info("volunteer_enrolled", roster_id=roster.id)
    return EnrollAck(edit_token=raw)


@router.get("/by-token/{token}", response_model=PersonalPageOut)
def get_personal_page(token: str, db: Session = Depends(get_db)) -> PersonalPageOut:
    return chores_svc.personal_page(db, _volunteer_by_token(db, token))


@router.put("/by-token/{token}", response_model=PersonalPageOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def update_enrolment(
    request: Request,
    token: str,
    data: EnrollEditIn,
    db: Session = Depends(get_db),
) -> PersonalPageOut:
    volunteer = _volunteer_by_token(db, token)
    _validate_chore_ids(db, volunteer.roster_id, data.chore_ids)

    # Replace the enrolment set.
    db.query(Enrollment).filter(Enrollment.volunteer_id == volunteer.id).delete()
    for cid in dict.fromkeys(data.chore_ids):
        db.add(Enrollment(volunteer_id=volunteer.id, chore_id=cid))
    volunteer.display_name = data.display_name

    # Reminder/email transitions (§6). The invariant held on every path:
    # email_reminders on ⇒ a ciphertext is on file; off ⇒ ciphertext NULL.
    email = data.email
    if data.email_reminders and (email is not None or volunteer.encrypted_email is not None):
        volunteer.email_reminders = True
        if email is not None:
            volunteer.encrypted_email = encryption.encrypt(email)
    else:
        volunteer.email_reminders = False
        volunteer.encrypted_email = None
    db.commit()
    return chores_svc.personal_page(db, volunteer)


@router.post("/by-token/{token}/leave", status_code=204)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def leave(request: Request, token: str, db: Session = Depends(get_db)) -> None:
    """Remove the volunteer. Enrolments cascade; the encrypted email goes
    with the row; future shifts drop the assignee via SET NULL."""
    volunteer = _volunteer_by_token(db, token)
    db.delete(volunteer)
    db.commit()
    logger.info("volunteer_left", roster_id=volunteer.roster_id)


def _shift_in_roster(db: Session, shift_id: str, roster_id: str) -> Shift:
    shift = (
        db.query(Shift)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(Shift.id == shift_id, Chore.roster_id == roster_id)
        .first()
    )
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found.")
    return shift


@router.post("/by-token/{token}/shifts/{shift_id}/done", response_model=PersonalPageOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def mark_shift_done(
    request: Request,
    token: str,
    shift_id: str,
    db: Session = Depends(get_db),
) -> PersonalPageOut:
    volunteer = _volunteer_by_token(db, token)
    shift = _shift_in_roster(db, shift_id, volunteer.roster_id)
    if shift.volunteer_id != volunteer.id:
        raise HTTPException(status_code=403, detail="This isn't your shift.")
    shift.status = "done"
    shift.done_at = datetime.now(UTC)
    db.commit()
    return chores_svc.personal_page(db, volunteer)


@router.post("/by-token/{token}/shifts/{shift_id}/handoff", response_model=PersonalPageOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def hand_off_shift(
    request: Request,
    token: str,
    shift_id: str,
    db: Session = Depends(get_db),
) -> PersonalPageOut:
    """Give up a shift. It reopens and is immediately re-assigned to
    someone else (excluding the bailer); if nobody is eligible it stays
    ``open`` for anyone to claim."""
    volunteer = _volunteer_by_token(db, token)
    shift = _shift_in_roster(db, shift_id, volunteer.roster_id)
    if shift.volunteer_id != volunteer.id:
        raise HTTPException(status_code=403, detail="This isn't your shift.")
    shift.volunteer_id = None
    shift.status = "open"
    chore_tick.reassign_shift(db, shift, exclude={volunteer.id})
    db.commit()
    return chores_svc.personal_page(db, volunteer)


@router.post("/by-token/{token}/shifts/{shift_id}/claim", response_model=PersonalPageOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def claim_shift(
    request: Request,
    token: str,
    shift_id: str,
    db: Session = Depends(get_db),
) -> PersonalPageOut:
    """Take an open shift on a chore you're enrolled for."""
    volunteer = _volunteer_by_token(db, token)
    shift = _shift_in_roster(db, shift_id, volunteer.roster_id)
    if shift.status != "open":
        raise HTTPException(status_code=409, detail="This shift is already taken.")
    enrolled = (
        db.query(Enrollment)
        .filter(Enrollment.volunteer_id == volunteer.id, Enrollment.chore_id == shift.chore_id)
        .first()
    )
    if enrolled is None:
        raise HTTPException(status_code=403, detail="You're not signed up for this chore.")
    shift.volunteer_id = volunteer.id
    shift.status = "scheduled"
    db.commit()
    return chores_svc.personal_page(db, volunteer)
