import io
import os
from datetime import UTC, datetime

import qrcode
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from uuid_utils import uuid7

from ..auth import require_approved
from ..database import get_db
from ..models import Event, Signup, User
from ..schemas.events import EventCreate, EventOut, EventStatsOut, SignupSummaryOut
from ..services import chapters as chapters_svc
from ..services import events as events_svc
from ..services import scd2 as scd2_svc
from ..services.ics import build_event_ics
from ..services.rate_limit import limiter
from ..services.slug import new_slug

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["events"])

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


def _attendees_for(db: Session, entity_id: str) -> int:
    total = db.query(func.coalesce(func.sum(Signup.party_size), 0)).filter(Signup.event_id == entity_id).scalar()
    return int(total or 0)


def _to_out(db: Session, event: Event) -> EventOut:
    """Build the public DTO. ``id`` is always ``entity_id`` — the
    stable logical id — so URLs and frontend caches survive every
    edit."""
    return EventOut(
        id=event.entity_id,
        slug=event.slug,
        name=event.name,
        topic=event.topic,
        location=event.location,
        latitude=event.latitude,
        longitude=event.longitude,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        source_options=event.source_options,
        help_options=event.help_options,
        questionnaire_enabled=event.questionnaire_enabled,
        reminder_enabled=event.reminder_enabled,
        locale=event.locale,
        chapter_id=event.chapter_id,
        chapter_name=chapters_svc.name_for_entity(db, event.chapter_id),
        signup_count=_attendees_for(db, event.entity_id),
    )


def _scope_filter(user: User):
    if user.chapter_id is None:
        return Event.chapter_id == "__no_match__"
    return Event.chapter_id == user.chapter_id


def _get_event_scoped(db: Session, entity_id: str, user: User) -> Event:
    """Fetch the current version of an event by entity_id, scoped to
    the user's chapter. 404 (not 403) so existence outside the
    chapter never leaks."""
    event = (
        scd2_svc.current(db.query(Event))
        .filter(Event.entity_id == entity_id, _scope_filter(user))
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("", response_model=EventOut, status_code=201)
def create_event(
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    if user.chapter_id is None:
        raise HTTPException(status_code=409, detail="No chapter assigned")
    now = datetime.now(UTC)
    new_id = str(uuid7())
    event = Event(
        id=new_id,
        entity_id=new_id,  # first version self-references
        slug=new_slug(),
        name=data.name,
        topic=data.topic,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        source_options=data.source_options,
        help_options=data.help_options,
        questionnaire_enabled=data.questionnaire_enabled,
        reminder_enabled=data.reminder_enabled,
        locale=data.locale,
        chapter_id=user.chapter_id,
        created_by=user.id,
        valid_from=now,
        valid_until=None,
        changed_by=user.id,
        change_kind="created",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info("event_created", event_id=event.entity_id, actor_id=user.id)
    return _to_out(db, event)


@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    rows = (
        scd2_svc.current(db.query(Event))
        .filter(_scope_filter(user), Event.archived_at.is_(None))
        .order_by(Event.starts_at.desc())
        .all()
    )
    return [_to_out(db, e) for e in rows]


@router.get("/archived", response_model=list[EventOut])
def list_archived_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[EventOut]:
    rows = (
        scd2_svc.current(db.query(Event))
        .filter(_scope_filter(user), Event.archived_at.is_not(None))
        .order_by(Event.created_at.desc())
        .all()
    )
    return [_to_out(db, e) for e in rows]


@router.post("/{entity_id}/archive", response_model=EventOut)
def archive_event(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = _get_event_scoped(db, entity_id, user)
    if event.archived_at is not None:
        raise HTTPException(status_code=409, detail="Already archived")
    new_row = scd2_svc.scd2_update(
        db,
        event,
        changed_by=user.id,
        change_kind="archived",
        archived_at=datetime.now(UTC),
    )
    db.commit()
    db.refresh(new_row)
    logger.info("event_archived", event_id=new_row.entity_id, actor_id=user.id)
    return _to_out(db, new_row)


@router.post("/{entity_id}/send-feedback-emails", status_code=200)
@limiter.limit("5/hour")
def send_feedback_emails_now(
    request: Request,
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> dict[str, int]:
    """Manually trigger the feedback worker for a single event."""
    from ..services import email_dispatcher
    from ..services.email_channels import FEEDBACK

    event = _get_event_scoped(db, entity_id, user)
    if not event.questionnaire_enabled:
        raise HTTPException(status_code=409, detail="Questionnaire is disabled for this event")
    processed = email_dispatcher.run_for_event(FEEDBACK, entity_id)
    logger.info("feedback_emails_triggered", event_id=entity_id, actor_id=user.id, processed=processed)
    return {"processed": processed}


@router.post("/{entity_id}/restore", response_model=EventOut)
def restore_event(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = _get_event_scoped(db, entity_id, user)
    if event.archived_at is None:
        raise HTTPException(status_code=409, detail="Not archived")
    new_row = scd2_svc.scd2_update(
        db,
        event,
        changed_by=user.id,
        change_kind="restored",
        archived_at=None,
    )
    db.commit()
    db.refresh(new_row)
    logger.info("event_restored", event_id=new_row.entity_id, actor_id=user.id)
    return _to_out(db, new_row)


@router.put("/{entity_id}", response_model=EventOut)
def update_event(
    entity_id: str,
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    event = _get_event_scoped(db, entity_id, user)
    was_questionnaire = event.questionnaire_enabled
    was_reminder = event.reminder_enabled
    new_row = scd2_svc.scd2_update(
        db,
        event,
        changed_by=user.id,
        change_kind="updated",
        name=data.name,
        topic=data.topic,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        source_options=data.source_options,
        help_options=data.help_options,
        questionnaire_enabled=data.questionnaire_enabled,
        reminder_enabled=data.reminder_enabled,
        locale=data.locale,
    )
    # Toggle-off cleanup: when an organiser disables a channel,
    # delete pending dispatches for it and wipe ciphertext for
    # signups that no longer have any pending dispatch.
    from ..models import EmailChannel
    from ..services import email_reaper

    retired: set[EmailChannel] = set()
    if was_questionnaire and not data.questionnaire_enabled:
        retired.add(EmailChannel.FEEDBACK)
    if was_reminder and not data.reminder_enabled:
        retired.add(EmailChannel.REMINDER)
    email_reaper.retire_event_channels(
        db, event_entity_id=new_row.entity_id, channels=retired
    )
    db.commit()
    db.refresh(new_row)
    logger.info("event_updated", event_id=new_row.entity_id, actor_id=user.id)
    return _to_out(db, new_row)


@router.get("/by-slug/{slug}", response_model=EventOut)
def get_event_by_slug(slug: str, db: Session = Depends(get_db)) -> EventOut:
    event = events_svc.get_public_event_by_slug(db, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _to_out(db, event)


@router.get("/by-slug/{slug}/event.ics")
def get_event_ics(slug: str, db: Session = Depends(get_db)) -> Response:
    """Public RFC 5545 calendar download for one event. Universal —
    Google, Apple, Outlook, Proton, Thunderbird, every mobile
    calendar app imports it. UID is the event's stable
    ``entity_id``, so re-importing after an organiser edit updates
    the existing entry instead of creating a duplicate."""
    event = events_svc.get_public_event_by_slug(db, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ics = build_event_ics(event, public_base_url=PUBLIC_BASE_URL)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8; method=PUBLISH",
        headers={
            "Content-Disposition": f'attachment; filename="event-{event.slug}.ics"',
            # Short cache — the file's contents change when the
            # organiser edits the event, but five minutes is fine
            # for the common "click, download, click again because
            # the first one didn't open" flow.
            "Cache-Control": "public, max-age=300",
        },
    )


@router.get("/by-slug/{slug}/qr.png")
def get_event_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    event = events_svc.get_public_event_by_slug(db, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    from qrcode.image.pil import PilImage

    target = f"{PUBLIC_BASE_URL}/e/{event.slug}"
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(target)
    qr.make(fit=True)
    pil_img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    img = pil_img.get_image().convert("RGBA")
    pixels = img.load()
    if pixels is not None:
        for y in range(img.height):
            for x in range(img.width):
                px = pixels[x, y]  # type: ignore[index]
                if isinstance(px, tuple) and px[0] == 255 and px[1] == 255 and px[2] == 255:
                    pixels[x, y] = (255, 255, 255, 0)  # type: ignore[index]
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/by-slug/{slug}/feedback-preview")
def feedback_form_preview(slug: str, db: Session = Depends(get_db)):
    """Preview of the post-event feedback form.

    The CTA in the feedback email's preview points here so an
    organiser can see exactly what attendees will fill in. No
    real ``FeedbackToken`` is involved — the SPA flags this
    response as a preview and disables the submit button.
    """
    from ..models import FeedbackQuestion
    from ..schemas.feedback import FeedbackFormOut, FeedbackQuestionOut

    event = events_svc.get_public_event_by_slug(db, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.questionnaire_enabled:
        raise HTTPException(status_code=404, detail="Channel disabled")

    questions = (
        db.query(FeedbackQuestion).order_by(FeedbackQuestion.ordinal).all()
    )
    return FeedbackFormOut(
        event_name=event.name,
        event_slug=event.slug,
        event_locale=event.locale,
        questions=[FeedbackQuestionOut.model_validate(q) for q in questions],
    )


@router.get("/by-slug/{slug}/email-preview/{channel}")
def email_preview(slug: str, channel: str, db: Session = Depends(get_db)) -> Response:
    """Render the exact email that the dispatcher will send to a
    signup on this event. Public, no auth — links from the
    privacy explainer use it to show the visitor what they're
    consenting to before leaving an email address.

    The feedback preview synthesises a placeholder ``?t=preview``
    URL since real per-signup tokens are minted only at send
    time."""
    from ..models import EmailChannel
    from ..services.email.templates import render
    from ..services.email_channels import spec_for

    event = events_svc.get_public_event_by_slug(db, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    try:
        ch = EmailChannel(channel)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown channel") from None

    # Channel must apply to this event — previewing an email
    # the visitor will never receive would mislead.
    if ch == EmailChannel.REMINDER and not event.reminder_enabled:
        raise HTTPException(status_code=404, detail="Channel disabled")
    if ch == EmailChannel.FEEDBACK and not event.questionnaire_enabled:
        raise HTTPException(status_code=404, detail="Channel disabled")

    spec = spec_for(ch)
    context = dict(spec.build_context(event))
    # In preview mode the absolute URLs that the dispatcher would
    # send (built off ``PUBLIC_BASE_URL``) might point to a port
    # other than the one hosting the SPA — in dev the API and SPA
    # are on different ports. Substitute relative paths so the
    # browser resolves them against whatever origin opened the
    # preview, which is always the SPA.
    if ch == EmailChannel.REMINDER:
        context["event_url"] = f"/e/{event.slug}"
    elif ch == EmailChannel.FEEDBACK:
        context["feedback_url"] = f"/e/{event.slug}/feedback?t=preview"

    _, html_body = render(spec.template_name, context, locale=event.locale)
    return Response(content=html_body, media_type="text/html; charset=utf-8")


@router.get("/{entity_id}/stats", response_model=EventStatsOut)
def event_stats(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventStatsOut:
    event = _get_event_scoped(db, entity_id, user)
    rows = (
        db.query(Signup.source_choice, func.count(Signup.id), func.sum(Signup.party_size))
        .filter(Signup.event_id == event.entity_id)
        .group_by(Signup.source_choice)
        .all()
    )
    total_signups = sum(int(c) for _, c, _ in rows)
    total_attendees = sum(int(s or 0) for _, _, s in rows)
    # Sign-ups that skipped the source question (NULL ``source_choice``)
    # still count toward the totals, but they don't show up in the
    # per-source breakdown — there's no bucket to put them in.
    by_source = {src: int(c) for src, c, _ in rows if src is not None}

    # ``by_help`` aggregates how many sign-ups opted into each
    # configured help_option. We tally in Python because help_choices
    # is JSON; the alternative is a JSON1 ``json_each`` join that
    # works on SQLite but not portably on Postgres without jsonb_path.
    by_help: dict[str, int] = {opt: 0 for opt in event.help_options}
    if event.help_options:
        choice_lists = (
            db.query(Signup.help_choices)
            .filter(Signup.event_id == event.entity_id)
            .all()
        )
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


@router.get("/{entity_id}/signups", response_model=list[SignupSummaryOut])
def event_signups(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[SignupSummaryOut]:
    """Per-signup list for the organiser details page. Returns
    display_name + party_size + help_choices — never email,
    source, or feedback-email status. Ordered by signup time
    (oldest first) so a list rendered next to running totals
    stays stable as new signups arrive at the bottom."""
    event = _get_event_scoped(db, entity_id, user)
    rows = (
        db.query(Signup.display_name, Signup.party_size, Signup.help_choices)
        .filter(Signup.event_id == event.entity_id)
        .order_by(Signup.created_at.asc())
        .all()
    )
    return [
        SignupSummaryOut(display_name=name, party_size=size, help_choices=help_choices or [])
        for name, size, help_choices in rows
    ]
