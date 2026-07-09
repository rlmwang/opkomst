"""Public-by-slug surfaces for one event.

Five endpoints, all keyed by the public 8-char slug, all
unauthenticated. Split out of the main events router because
they share zero auth + scope code with the chapter-scoped
organiser CRUD.

* ``GET /by-slug/{slug}`` — the JSON the public form reads.
* ``GET /by-slug/{slug}/event.ics`` — RFC 5545 calendar download.
* ``GET /by-slug/{slug}/qr.svg`` — QR code that resolves to
  ``PUBLIC_BASE_URL/e/{slug}``.
* ``GET /by-slug/{slug}/feedback-preview`` — questionnaire DTO
  rendered as it would appear after redeeming a feedback token.
* ``GET /by-slug/{slug}/email-preview/{channel}`` — exact HTML
  the dispatcher would render for that channel.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import EmailChannel, Occurrence
from ..schemas.events import PublicEventOut
from ..schemas.feedback import FeedbackFormOut, FeedbackQuestionOut
from ..services import events as events_svc
from ..services import mail_lifecycle
from ..services.feedback_questions import QUESTIONS
from ..services.ics import build_occurrence_ics
from ..services.mail import build_url, render
from ..services.qr import render_qr

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# Public-facing base URL for QR codes and ICS links. Validated at
# import time (HttpUrl) — never empty.
PUBLIC_BASE_URL = str(settings.public_base_url).rstrip("/")


def _resolve_occurrence(db: Session, slug: str, *, allow_archived: bool = False) -> Occurrence:
    """Resolve a slug to an occurrence (the public page is per occurrence),
    its event eager-loaded. ``allow_archived=True`` for the public
    ``GET /by-slug`` so the page can render a soft "this event has been
    archived" state. Share surfaces (ICS, QR, previews) keep
    ``allow_archived=False`` — no point handing out a calendar invite for
    an archived event."""
    occurrence = (
        events_svc.get_occurrence_by_slug_any(db, slug)
        if allow_archived
        else events_svc.get_public_occurrence_by_slug(db, slug)
    )
    if not occurrence:
        raise HTTPException(status_code=404, detail="Event not found")
    return occurrence


def _resolve_channel(channel: str) -> EmailChannel:
    try:
        return EmailChannel(channel)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown channel") from None


@router.get("/by-slug/{slug}", response_model=PublicEventOut)
def get_event_by_slug(slug: str, response: Response, db: Session = Depends(get_db)) -> PublicEventOut:
    """Public event lookup. The response is identical for every
    visitor in the seconds between two organiser edits, so it's a
    perfect candidate for HTTP caching: a 60 s shared cache window
    (Coolify/Traefik / any CDN that fronts the app) keeps the
    common case off the DB entirely, and ``stale-while-revalidate``
    means a request after the 60 s expiry serves the still-warm
    payload while a single background fetch refreshes it.

    The 60 s freshness window is the trade-off: an organiser edit
    is visible to *new* visitors after up to 60 s. Acceptable —
    edits during an active sign-up window are rare, and
    ``no-store`` would defeat the point of caching the highest-
    traffic public endpoint."""
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
    return events_svc.build_public_event(db, _resolve_occurrence(db, slug, allow_archived=True))


@router.get("/by-slug/{slug}/event.ics")
def get_event_ics(slug: str, db: Session = Depends(get_db)) -> Response:
    """Public RFC 5545 calendar download for one event. Universal —
    Google, Apple, Outlook, Proton, Thunderbird, every mobile
    calendar app imports it. UID is the event's stable ``id``,
    so re-importing after an organiser edit updates the existing
    entry instead of creating a duplicate."""
    occurrence = _resolve_occurrence(db, slug)
    ics = build_occurrence_ics(occurrence, occurrence.event, public_base_url=PUBLIC_BASE_URL)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8; method=PUBLISH",
        headers={
            "Content-Disposition": f'attachment; filename="event-{occurrence.slug}.ics"',
            "Cache-Control": "public, max-age=300",
        },
    )


@router.get("/by-slug/{slug}/qr.svg")
def get_event_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    occurrence = _resolve_occurrence(db, slug)
    return Response(
        content=render_qr(f"{PUBLIC_BASE_URL}/e/{occurrence.slug}"),
        media_type="image/svg+xml",
        # Browser-side cache complements the in-process LRU: 24h
        # turns repeat dashboard visits into 304 Not Modified.
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/by-slug/{slug}/feedback-preview")
def feedback_form_preview(slug: str, db: Session = Depends(get_db)) -> FeedbackFormOut:
    """Preview of the post-event feedback form."""
    occurrence = _resolve_occurrence(db, slug)
    event = occurrence.event
    if not event.feedback_enabled:
        raise HTTPException(status_code=404, detail="Channel disabled")

    return FeedbackFormOut(
        event_name=event.name,
        event_slug=occurrence.slug,
        event_locale=event.locale,
        questions=[
            FeedbackQuestionOut(key=q.key, ordinal=q.ordinal, kind=q.kind, required=q.required) for q in QUESTIONS
        ],
    )


@router.get("/by-slug/{slug}/email-preview/{channel}")
def email_preview(slug: str, channel: str, db: Session = Depends(get_db)) -> Response:
    """Render the exact email that the dispatcher will send to a
    signup on this event."""
    occurrence = _resolve_occurrence(db, slug)
    event = occurrence.event
    ch = _resolve_channel(channel)

    if not mail_lifecycle.channel_enabled_for(ch, event):
        raise HTTPException(status_code=404, detail="Channel disabled")
    cdef = mail_lifecycle.CHANNELS[ch]
    context = dict(cdef.context(occurrence, event))
    if ch == EmailChannel.FEEDBACK:
        context["feedback_url"] = build_url(f"e/{occurrence.slug}/feedback", t="preview")

    _, html_body = render(cdef.template, context, locale=event.locale)
    return Response(content=html_body, media_type="text/html; charset=utf-8")
