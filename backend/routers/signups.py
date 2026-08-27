"""Public sign-up (booking) + booking-edit endpoints.

A booking is an order with line items: one ``Registration`` (the person,
their party size, and the single edit link) with one ``Signup`` line item
per occurrence they picked. Signing up for one occurrence and signing up
for the whole course are the same shape — a registration with one or many
line items. Reminder/feedback mail is per occurrence: each line item's
occurrence gets its own dispatch rows, carrying their own encrypted copy
of the address, decoupled from the booking (no ``signup_id`` /
``registration_id`` link — principle #2).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import EmailChannel, EmailDispatch, EmailStatus, Event, Occurrence, Registration, Signup, User
from ..schemas.common import EditLinkRecoverOut, pick_localized
from ..schemas.events import (
    BookingEditIn,
    BookingOccurrenceOut,
    BookingOccurrencesIn,
    BookingOut,
    SignupAck,
    SignupCreate,
)
from ..services import access, edit_token, encryption, event_recurrence, limits, public_access, traffic
from ..services import events as events_svc
from ..services.events import now_wallclock
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["signups"])


def _resolve_targets(db: Session, event: Event, data: SignupCreate, now) -> list[Occurrence]:
    """The occurrences a booking should cover. ``all_upcoming`` resolves
    server-side to every materialised occurrence still in the future, so a
    stale page can't book a session already past. Otherwise the posted
    ids, each validated to belong to this event and not be over yet."""
    live = db.query(Occurrence).filter(Occurrence.event_id == event.id, Occurrence.ends_at > now)
    if data.all_upcoming:
        targets = live.order_by(Occurrence.starts_at.asc()).all()
        if not targets:
            raise HTTPException(status_code=409, detail="This event has no upcoming sessions to sign up for.")
        return targets
    targets = live.filter(Occurrence.id.in_(data.occurrence_ids)).all()
    if len(targets) != len(data.occurrence_ids):
        raise HTTPException(status_code=400, detail="One or more selected sessions are unavailable.")
    return sorted(targets, key=lambda o: o.starts_at)


@router.post("/by-slug/{slug}/signups", response_model=SignupAck, status_code=201)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def create_signup(
    request: Request,
    slug: str,
    data: SignupCreate,
    db: Session = Depends(get_db),
) -> SignupAck:
    occurrence = events_svc.get_public_occurrence_by_slug(db, slug)
    if not occurrence:
        raise HTTPException(status_code=404, detail="Event not found")
    event = occurrence.event
    # A switched-off question isn't asked, so an answer to it is a stale
    # page or a hand-made request, not something to record.
    allowed_sources = event.source_options if event.source_enabled else []
    allowed_help = event.help_options if event.help_enabled else []
    if data.source_choice is not None and data.source_choice not in allowed_sources:
        raise HTTPException(status_code=400, detail="source_choice must match one of the event's options")
    invalid_help = [c for c in data.help_choices if c not in allowed_help]
    if invalid_help:
        raise HTTPException(
            status_code=400,
            detail=f"help_choices must be a subset of the event's help_options: {invalid_help}",
        )

    now = now_wallclock()
    targets = _resolve_targets(db, event, data, now)
    # A personal account's event holds a bounded number of people; an
    # organisation's has no ceiling. A party counts for everyone it
    # brings. The visitor is told only that it is full, never how full
    # and never whose account it is.
    public_access.assert_name_given(event, data.display_name)
    limits.assert_has_room_for_participant(db, event.tenant, "event", event.id, data.party_size)

    # One booking (order header) holding the single edit link, pseudonym
    # and party size.
    raw_token, token_hash = edit_token.new_edit_token()
    registration = Registration(
        event_id=event.id,
        display_name=data.display_name,
        party_size=data.party_size,
        edit_token_hash=token_hash,
    )
    db.add(registration)
    db.flush()

    has_email = bool(data.email)
    total_dispatches = 0
    for occ in targets:
        db.add(
            Signup(
                registration_id=registration.id,
                occurrence_id=occ.id,
                source_choice=data.source_choice,
                help_choices=data.help_choices,
            )
        )
        # Per-occurrence dispatch rows. Reminders apply only when the
        # occurrence hasn't started yet (the worker's window would skip a
        # past-start row); feedback applies whenever its toggle is on. Each
        # dispatch carries its own encrypted copy of the address and points
        # at the occurrence — never at the booking or line item.
        channels: list[EmailChannel] = []
        if has_email and event.feedback_enabled:
            channels.append(EmailChannel.FEEDBACK)
        if has_email and event.reminder_enabled and occ.starts_at > now:
            channels.append(EmailChannel.REMINDER)
        for ch in channels:
            assert data.email is not None  # has_email gate
            db.add(
                EmailDispatch(
                    occurrence_id=occ.id,
                    channel=ch,
                    status=EmailStatus.PENDING,
                    encrypted_email=encryption.encrypt(data.email),
                    # Mail this attendee in the language they signed up in;
                    # fall back to the event's primary locale.
                    locale=data.locale or event.locale,
                )
            )
            total_dispatches += 1
    db.commit()
    logger.info(
        "signup_created",
        event_id=event.id,
        party_size=data.party_size,
        occurrences=len(targets),
        dispatches=total_dispatches,
    )
    traffic.record("public_event", "submit")
    return SignupAck(edit_token=raw_token)


def _registration_by_token(db: Session, token: str) -> Registration:
    """Resolve an edit-link token to its booking. 404 if no match; 410 if
    the event is archived. The registration carries no email and no key to
    its dispatch rows, so this read-back can't reach any address."""
    return public_access.resolve_by_token(
        db,
        Registration,
        token,
        parent_model=Event,
        parent_fk=Registration.event_id,
        gone_detail="This event is no longer open for changes.",
    )


def _booking_out(db: Session, registration: Registration) -> BookingOut:
    event = db.query(Event).filter(Event.id == registration.event_id).first()
    assert event is not None  # _registration_by_token already proved it
    now = now_wallclock()
    rows = (
        db.query(Signup, Occurrence)
        .join(Occurrence, Occurrence.id == Signup.occurrence_id)
        .filter(Signup.registration_id == registration.id)
        .order_by(Occurrence.starts_at.asc())
        .all()
    )
    return BookingOut(
        display_name=registration.display_name,
        party_size=registration.party_size,
        link_recovered_at=registration.link_recovered_at,
        event_name=pick_localized(event.name_nl, event.name_en, event.locale) or "",
        event_slug=event.slug,
        locale=event.locale,
        occurrences=[
            BookingOccurrenceOut(
                occurrence_id=occ.id,
                slug=occ.slug,
                index=event_recurrence.session_index(event, occ.starts_at.date()),
                starts_at=occ.starts_at,
                ends_at=occ.ends_at,
                is_past=occ.starts_at <= now,
                source_choice=signup.source_choice,
                help_choices=signup.help_choices or [],
            )
            for signup, occ in rows
        ],
    )


@router.get("/by-token/{token}", response_model=BookingOut)
def get_booking(token: str, db: Session = Depends(get_db)) -> BookingOut:
    """The whole booking behind an edit-link token, for the edit page.
    Email is never returned (it isn't reachable from a booking)."""
    return _booking_out(db, _registration_by_token(db, token))


@router.put("/by-token/{token}", response_model=BookingOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def update_booking(
    request: Request,
    token: str,
    data: BookingEditIn,
    db: Session = Depends(get_db),
) -> BookingOut:
    """Update a booking's name + party size via its edit-link token.
    Email + dispatch rows are untouched — there is no path from a booking
    to its encrypted address (principle #2)."""
    registration = _registration_by_token(db, token)
    # Growing a party takes places just like a new booking does, so the
    # ceiling is checked on the difference. Shrinking passes trivially:
    # a negative delta always leaves room.
    booked_event = db.query(Event).filter(Event.id == registration.event_id).one()
    public_access.assert_answers_editable(booked_event)
    limits.assert_has_room_for_participant(
        db,
        booked_event.tenant,
        "event",
        booked_event.id,
        data.party_size - registration.party_size,
    )
    public_access.assert_name_given(booked_event, data.display_name)
    registration.display_name = data.display_name
    registration.party_size = data.party_size
    db.commit()
    logger.info("booking_edited", registration_id=registration.id)
    return _booking_out(db, registration)


@router.post("/by-token/{token}/occurrences/{occurrence_id}/withdraw", status_code=204)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def withdraw_occurrence(
    request: Request,
    token: str,
    occurrence_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Withdraw the booking from one occurrence — per-occurrence withdrawal
    is how absence is reported. Deletes only that ``Signup`` line item (no
    email lives on it). If it was the booking's last line item, the empty
    ``Registration`` is deleted too. Any pending ``EmailDispatch`` for the
    occurrence is untouched by design (no signup link), so an already-
    scheduled email may still arrive."""
    registration = _registration_by_token(db, token)
    row = (
        db.query(Signup, Occurrence)
        .join(Occurrence, Occurrence.id == Signup.occurrence_id)
        .filter(Signup.registration_id == registration.id, Signup.occurrence_id == occurrence_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="This booking is not on that session.")
    line_item, occurrence = row
    # A session that has already started is frozen attendance history; you
    # can't undo it after the fact.
    if occurrence.starts_at <= now_wallclock():
        raise HTTPException(status_code=409, detail="This session has already started and can't be changed.")
    db.delete(line_item)
    db.flush()
    remaining = db.query(Signup.id).filter(Signup.registration_id == registration.id).first()
    if remaining is None:
        db.delete(registration)
    db.commit()
    logger.info("occurrence_withdrawn", registration_id=registration.id, occurrence_id=occurrence_id)


@router.put("/by-token/{token}/occurrences", response_model=BookingOut)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def set_booking_occurrences(
    request: Request,
    token: str,
    data: BookingOccurrencesIn,
    db: Session = Depends(get_db),
) -> BookingOut:
    """Replace a booking's **future** session set from the manage-page
    calendar. Diffs the chosen future occurrences against the booking's
    current future line items: adds a line item for each newly-selected
    occurrence, deletes it for each deselected one, and never touches a line
    item whose session has already started (frozen attendance).

    ``all_upcoming`` resolves server-side to every future occurrence, so a
    stale page can't miss a just-materialised session. Newly-added sessions
    get a line item only, not an email dispatch: the recipient address isn't
    reachable from a booking (principle #2), so reminder/feedback mail only
    ever covers sessions signed up for with an email at sign-up time."""
    registration = _registration_by_token(db, token)
    public_access.assert_answers_editable(db.query(Event).filter(Event.id == registration.event_id).one())
    now = now_wallclock()

    live = db.query(Occurrence).filter(Occurrence.event_id == registration.event_id, Occurrence.starts_at > now)
    if data.all_upcoming:
        desired_ids = {o.id for o in live.all()}
    else:
        found = live.filter(Occurrence.id.in_(data.occurrence_ids)).all()
        if len(found) != len(data.occurrence_ids):
            raise HTTPException(status_code=400, detail="One or more selected sessions are unavailable.")
        desired_ids = {o.id for o in found}

    rows = (
        db.query(Signup, Occurrence)
        .join(Occurrence, Occurrence.id == Signup.occurrence_id)
        .filter(Signup.registration_id == registration.id)
        .all()
    )
    current_future = {occ.id: su for su, occ in rows if occ.starts_at > now}
    # New line items inherit the booking's original "how did you hear" + help
    # choices (identical across its line items at sign-up time).
    template = rows[0][0] if rows else None
    source_choice = template.source_choice if template else None
    help_choices = list(template.help_choices or []) if template else []

    for occ_id in desired_ids - set(current_future):
        db.add(
            Signup(
                registration_id=registration.id,
                occurrence_id=occ_id,
                source_choice=source_choice,
                help_choices=help_choices,
            )
        )
    for occ_id in set(current_future) - desired_ids:
        db.delete(current_future[occ_id])

    db.commit()
    db.refresh(registration)
    logger.info(
        "booking_occurrences_set",
        registration_id=registration.id,
        added=len(desired_ids - set(current_future)),
        removed=len(set(current_future) - desired_ids),
    )
    return _booking_out(db, registration)


@router.post("/by-token/{token}/withdraw", status_code=204)
@limiter.limit(Limits.PUBLIC_SIGNUP)
def withdraw_booking(request: Request, token: str, db: Session = Depends(get_db)) -> None:
    """Withdraw the whole booking — the attendee removing themselves from
    every occurrence at once. Deletes the ``Registration`` (its line items
    cascade). Pending dispatches are untouched by design."""
    registration = _registration_by_token(db, token)
    db.delete(registration)
    db.commit()
    logger.info("booking_withdrawn", registration_id=registration.id)


@router.post("/{event_id}/registrations/{registration_id}/edit-link", response_model=EditLinkRecoverOut)
@limiter.limit(Limits.ORG_WRITE)
def recover_booking_edit_link(
    request: Request,
    event_id: str,
    registration_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EditLinkRecoverOut:
    """Organiser recovery of a participant's lost magic link. Only the
    token's hash is stored, so this *rotates* rather than reveals: the old
    link stops working, the fresh raw token is returned exactly once, and
    ``link_recovered_at`` is stamped permanently."""
    event = access.get_event_for_user(db, event_id, user)
    registration = (
        db.query(Registration).filter(Registration.id == registration_id, Registration.event_id == event.id).first()
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    raw = edit_token.recover(registration)
    db.commit()
    logger.info("booking_edit_link_recovered", event_id=event.id, registration_id=registration_id, actor_id=user.id)
    return EditLinkRecoverOut(edit_token=raw)


@router.delete("/{event_id}/signups/{signup_id}", status_code=204)
@limiter.limit(Limits.ORG_WRITE)
def delete_signup(
    request: Request,
    event_id: str,
    signup_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Organiser-only hard-delete of a single sign-up line item — a stray
    or duplicate booking on one occurrence. Privacy invariant unaffected:
    ``Signup`` carries no email. Any pending ``EmailDispatch`` for the
    occurrence lives on by design (no signup link)."""
    event = access.get_event_for_user(db, event_id, user)
    line_item = (
        db.query(Signup)
        .join(Occurrence, Occurrence.id == Signup.occurrence_id)
        .filter(Signup.id == signup_id, Occurrence.event_id == event.id)
        .first()
    )
    if line_item is None:
        raise HTTPException(status_code=404, detail="Signup not found")
    registration_id = line_item.registration_id
    db.delete(line_item)
    db.flush()
    # Deleting the last line item leaves an empty booking — drop it too.
    remaining = db.query(Signup.id).filter(Signup.registration_id == registration_id).first()
    if remaining is None:
        db.query(Registration).filter(Registration.id == registration_id).delete()
    db.commit()
    logger.info("signup_deleted", event_id=event.id, signup_id=signup_id, actor_id=user.id)
