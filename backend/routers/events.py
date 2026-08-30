"""Chapter-scoped event CRUD + organiser-side reads.

Five mutating endpoints (create / update / archive / restore /
send-emails-now) and four read endpoints (list / list-archived /
stats / signups). All require an approved user; all are scoped
to the user's chapter via ``access.get_event_for_user`` (single)
or ``_scope_filter`` (lists).

Public-by-slug surfaces (ICS, QR, previews, the JSON the public
form reads) live in ``routers/events_public.py``.

Read aggregates (chapter-name + attendee-total enrichment, source/
help breakdowns, signups summary) live in ``services/event_stats.py``
where they can be unit-tested without a router fixture.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..config import settings
from ..database import get_db
from ..models import EmailChannel, Event, EventHelpOption, EventSourceOption, Occurrence, User
from ..schemas.common import Page
from ..schemas.events import (
    EventCreate,
    EventListOut,
    EventOut,
    EventPageOut,
    EventStatsOut,
    EventUpdate,
    SignupSummaryOut,
)
from ..services import access, crud, entities, event_recurrence, event_stats, feedback_stats, limits, mail_lifecycle
from ..services import events as events_svc
from ..services import image as image_svc
from ..services.events import now_wallclock
from ..services.paging import DEFAULT_PER_PAGE, MAX_PER_PAGE, Paging
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/event", tags=["events"])


@router.post("", response_model=EventOut, status_code=201)
@limiter.limit(Limits.ORG_RARE)
def create_event(
    request: Request,
    data: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    # Caller-supplied chapter must be one the user actually
    # belongs to. The frontend's chapter dropdown is already
    # scoped to the user's live chapters; this is the
    # defence-in-depth check.
    access.assert_user_can_assign_chapter(db, user, data.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "event")
    event = entities.create_event(db, data, user)
    db.commit()
    db.refresh(event)
    return event_stats.to_out(db, event)


@router.get("", response_model=Page[EventListOut])
def list_events(
    chapter_id: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE),
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> Page[EventListOut]:
    """One page of the organiser's events, what is coming first.

    The search and the order are the statement's: the browser used to
    do both over every row it had been sent."""
    return event_stats.list_for_user(db, user, chapter_id, Paging(page, per_page, q))


@router.get("/archived", response_model=Page[EventListOut])
def list_archived_events(
    chapter_id: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE),
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> Page[EventListOut]:
    # Archived events are not in ``events`` any more; they are in its
    # twin, with ``archive_index`` holding when each left. The rows come
    # back as mappings rather than ORM objects, because there is no live
    # row for the ORM to be about.
    window = Paging(page, per_page, q)
    rows, total = access.archived_rows(db, "events", user, chapter_id, page=window)
    return window.of(total, event_stats.archived_enrich(db, rows))


@router.post("/{event_id}/archive", response_model=EventOut)
@limiter.limit(Limits.ORG_RARE)
def archive_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = access.get_event_for_user(db, event_id, user)
    # Projected before the move: afterwards there is no live row to read.
    out = event_stats.to_out(db, event)
    crud.archive_entity(db, event, root="events", log_event="event_archived", actor_id=user.id)
    # The projection was taken while the event was still live; the call
    # it is answering is what made it archived.
    return out.model_copy(update={"archived": True})


@router.post("/{event_id}/restore", response_model=EventOut)
@limiter.limit(Limits.ORG_RARE)
def restore_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    access.archived_row(db, "events", event_id, user)
    crud.restore_entity(db, root="events", entity_id=event_id, log_event="event_restored", actor_id=user.id)
    return event_stats.to_out(
        db,
        access.get_scoped_row(db, Event, event_id, user, *event_stats.FULL_COLUMNS, not_found="Event not found"),
    )


@router.delete("/{event_id}", status_code=204)
@limiter.limit(Limits.ORG_RARE)
def delete_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Delete an archived event for good. A live event is not found
    here at all — it is in ``events``, and this reads the archive — so
    deleting one still means archiving it first. The item's whole graph
    goes, plus the image it owned."""
    row = access.archived_row(db, "events", event_id, user)
    crud.purge_entity(
        db,
        root="events",
        entity_id=event_id,
        image_path=row["image_path"],
        log_event="event_deleted",
        actor_id=user.id,
    )


@router.post("/{event_id}/send-emails/{channel}", status_code=200)
@limiter.limit(Limits.SEND_EMAILS_NOW)
def send_emails_now(
    request: Request,
    event_id: str,
    channel: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> dict[str, int]:
    """Manually trigger the worker for one channel on a single
    event. Re-use of the generic dispatcher means the reminder
    + feedback "send now" buttons share one endpoint and one
    rate-limit budget."""
    event = access.get_event_for_user(db, event_id, user)
    try:
        ch = EmailChannel(channel)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown channel") from None
    if not mail_lifecycle.channel_enabled_for(ch, event):
        raise HTTPException(status_code=409, detail=f"Channel {ch.value} is disabled for this event")
    processed = mail_lifecycle.run_for_event(ch, event_id)
    logger.info(
        "emails_triggered",
        event_id=event_id,
        channel=channel,
        actor_id=user.id,
        processed=processed,
    )
    return {"processed": processed}


@router.put("/{event_id}", response_model=EventOut)
@limiter.limit(Limits.ORG_WRITE)
def update_event(
    request: Request,
    event_id: str,
    data: EventUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    event = access.get_event_for_user(db, event_id, user)
    if data.reminder_enabled or data.feedback_enabled:
        limits.assert_can_send_participant_mail(user.tenant)
    was_feedback = event.feedback_enabled
    was_reminder = event.reminder_enabled

    # Chapter changes are allowed (the user might've picked the
    # wrong chapter at create time) but the new one still has to
    # be in the user's set, same as create.
    if data.chapter_id != event.chapter_id:
        access.assert_user_can_assign_chapter(db, user, data.chapter_id)

    event.name_nl = data.name_nl
    event.name_en = data.name_en
    event.chapter_id = data.chapter_id
    event.topic_nl = data.topic_nl
    event.topic_en = data.topic_en
    event.location = data.location
    event.latitude = data.latitude
    event.longitude = data.longitude
    event.starts_on = data.starts_on
    event.start_time = data.start_time
    event.end_time = data.end_time
    event.period_weeks = data.period_weeks
    event.cycle_slots = data.cycle_slots
    event.span_weeks = data.span_weeks
    event.horizon_days = data.horizon_days
    if not data.confirm_destructive:
        doomed = events_svc.count_destroyed_answers(db, event, data.source_options, data.help_options)
        if doomed:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This removes {doomed} given {'answer' if doomed == 1 else 'answers'}. Save again to confirm."
                ),
            )
    events_svc.apply_options(db, event, EventSourceOption, event.source_options, data.source_options)
    event.source_enabled = data.source_enabled
    events_svc.apply_options(db, event, EventHelpOption, event.help_options, data.help_options)
    event.help_enabled = data.help_enabled
    event.feedback_enabled = data.feedback_enabled
    event.reminder_enabled = data.reminder_enabled
    event.listed = data.listed
    event.name_required = data.name_required
    event.answers_editable = data.answers_editable
    event.locale = data.locale
    event.image_artist_instagram = data.image_artist_instagram

    # A rule change re-points / prunes future occurrences (keeping any that
    # already have sign-ups) and materialises newly in-horizon dates. Past
    # occurrences are frozen. Content changes need no propagation — every
    # occurrence reads content through the event.
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())

    # Toggle-off cleanup: when an organiser disables a channel, delete
    # pending dispatches for it across the event's occurrences.
    retired: set[EmailChannel] = set()
    if was_feedback and not data.feedback_enabled:
        retired.add(EmailChannel.FEEDBACK)
    if was_reminder and not data.reminder_enabled:
        retired.add(EmailChannel.REMINDER)
    mail_lifecycle.retire_event_channels(db, event_id=event.id, channels=retired)
    db.commit()
    db.refresh(event)
    logger.info("event_updated", event_id=event.id, actor_id=user.id)
    return event_stats.to_out(db, event)


@router.post("/{event_id}/image", response_model=EventOut)
@limiter.limit(Limits.ORG_RARE)
def upload_event_image(
    request: Request,
    event_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    """Upload (or replace) the event's hero image. The bytes go
    through ``services/image.py``: validated, EXIF-rotated, cropped to
    4:5, resized to 1200x1500, JPEG-re-encoded, then stored.
    ``event.image_path`` is set to where it landed, and what anyone
    sees is this app's own ``/i/{path}``.

    Replacing an image deletes the file it replaces, once the row
    points at the new one.

    Returns the updated ``EventOut`` so the caller's query
    cache patches in-place without an extra refetch."""
    if not settings.event_images_enabled:
        logger.warning("event_image_upload_disabled", event_id=event_id, actor_id=user.id)
        raise HTTPException(status_code=503, detail="Event-image storage is not configured")
    event = access.get_event_for_user(db, event_id, user)
    # Sync ``def``, so this runs in the threadpool: the processing and
    # the upload that follow both block (``services/image.py``).
    raw = file.file.read()
    try:
        jpeg = image_svc.process_upload(raw)
    except image_svc.ImageProcessingError as exc:
        logger.warning(
            "event_image_process_failed",
            event_id=event.id,
            actor_id=user.id,
            content_type=file.content_type,
            raw_bytes=len(raw),
            reason=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
    previous = event.image_path
    try:
        path = image_svc.store(
            folder="events",
            entity_id=event.id,
            timestamp_ms=timestamp_ms,
            jpeg_bytes=jpeg,
        )
    except image_svc.GithubUploadError as exc:
        logger.warning(
            "event_image_github_upload_failed",
            event_id=event.id,
            actor_id=user.id,
            reason=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    event.image_path = path
    db.commit()
    db.refresh(event)
    # After the row points at the new file, so a failed upload leaves
    # the event with the picture it had.
    if previous and previous != path:
        image_svc.delete(previous)
    logger.info("event_image_uploaded", event_id=event.id, actor_id=user.id)
    return event_stats.to_out(db, event)


@router.delete("/{event_id}/image", response_model=EventOut)
@limiter.limit(Limits.ORG_RARE)
def delete_event_image(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    """Clear the reference and delete the file. Nothing else points at
    it, so leaving it behind would be storage nobody can ever reach."""
    event = access.get_event_for_user(db, event_id, user)
    if event.image_path is None:
        # 404 over 204 so the frontend can distinguish "no-op" from
        # "succeeded"; the user clicked Delete on a row that
        # already had nothing.
        raise HTTPException(status_code=404, detail="No image to delete")
    dropped = event.image_path
    event.image_path = None
    db.commit()
    image_svc.delete(dropped)
    db.refresh(event)
    logger.info("event_image_deleted", event_id=event.id, actor_id=user.id)
    return event_stats.to_out(db, event)


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventOut:
    """One event. The detail and edit pages read the event they are
    about from here; they used to filter it out of the full list, which
    made opening either one cost every event in the chapter."""
    return event_stats.to_out(
        db,
        access.get_scoped_row(db, Event, event_id, user, *event_stats.FULL_COLUMNS, not_found="Event not found"),
    )


def _page_event(db: Session, event_id: str, user: User) -> Any:
    """The event row the occurrence panel needs: the recurrence rule,
    which is what the projected dates come out of."""
    return access.get_scoped_row(
        db,
        Event,
        event_id,
        user,
        Event.id,
        Event.cycle_slots,
        Event.span_weeks,
        Event.period_weeks,
        Event.starts_on,
        Event.start_time,
        Event.end_time,
        Event.horizon_days,
        not_found="Event not found",
    )


@router.get("/{event_id}/page", response_model=EventPageOut)
def event_page(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventPageOut:
    """The whole organiser page in one read.

    The six routes below and above still exist, because switching to
    another session asks for that session's sign-ups and stats. What
    they stopped being is the way the page opens."""
    event = access.get_event_for_user(db, event_id, user)
    occurrences, primary_id = event_stats.occurrence_list(db, event)
    primary = db.query(Occurrence).filter(Occurrence.id == primary_id).first() if primary_id is not None else None
    return EventPageOut(
        event=event_stats.to_out(db, event),
        occurrences=occurrences,
        primary_occurrence_id=primary_id,
        signups=event_stats.occurrence_signups_summary(db, primary) if primary else [],
        stats=event_stats.per_occurrence_stats(db, primary, event.help_options)
        if primary
        else EventStatsOut(total_signups=0, total_attendees=0, by_source={}, by_help={}),
        feedback=feedback_stats.summary(db, event_id),
    )


@router.get("/{event_id}/occurrences/{occurrence_id}/signups", response_model=list[SignupSummaryOut])
def occurrence_signups(
    event_id: str,
    occurrence_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[SignupSummaryOut]:
    """Per-line-item list for one occurrence of the organiser's event.
    Returns display_name + party_size + help_choices — never email,
    source, or feedback-email status."""
    event = access.get_event_for_user(db, event_id, user)
    occurrence = db.query(Occurrence).filter(Occurrence.id == occurrence_id, Occurrence.event_id == event.id).first()
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    return event_stats.occurrence_signups_summary(db, occurrence)


@router.get("/{event_id}/occurrences/{occurrence_id}/stats", response_model=EventStatsOut)
def occurrence_stats(
    event_id: str,
    occurrence_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EventStatsOut:
    """Aggregated source/help breakdown for one occurrence — the "stats of
    that day" behind the detail page's calendar day switcher. Aggregate
    only, never linked to a person."""
    event = access.get_event_for_user(db, event_id, user)
    occurrence = db.query(Occurrence).filter(Occurrence.id == occurrence_id, Occurrence.event_id == event.id).first()
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    return event_stats.per_occurrence_stats(db, occurrence, event.help_options)
