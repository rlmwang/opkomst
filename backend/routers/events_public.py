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

import io
from functools import lru_cache

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import EmailChannel
from ..schemas.events import EventOut
from ..schemas.feedback import FeedbackFormOut, FeedbackQuestionOut
from ..services import event_stats, mail_lifecycle
from ..services import events as events_svc
from ..services.feedback_questions import QUESTIONS
from ..services.ics import build_event_ics
from ..services.mail import build_url, render

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# Public-facing base URL for QR codes and ICS links. Validated at
# import time (HttpUrl) — never empty.
PUBLIC_BASE_URL = str(settings.public_base_url).rstrip("/")


def _resolve_event(db: Session, slug: str, *, allow_archived: bool = False):
    """Resolve a slug to an event. ``allow_archived=True`` for the
    public ``GET /by-slug`` so the page can render a soft
    "this event has been archived" state. Share surfaces (ICS,
    QR, previews) keep ``allow_archived=False`` — no point
    handing out a calendar invite for an archived event."""
    event = (
        events_svc.get_event_by_slug_any(db, slug) if allow_archived else events_svc.get_public_event_by_slug(db, slug)
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _resolve_channel(channel: str) -> EmailChannel:
    try:
        return EmailChannel(channel)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown channel") from None


@router.get("/by-slug/{slug}", response_model=EventOut)
def get_event_by_slug(slug: str, response: Response, db: Session = Depends(get_db)) -> EventOut:
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
    return event_stats.to_out(db, _resolve_event(db, slug, allow_archived=True))


@router.get("/by-slug/{slug}/event.ics")
def get_event_ics(slug: str, db: Session = Depends(get_db)) -> Response:
    """Public RFC 5545 calendar download for one event. Universal —
    Google, Apple, Outlook, Proton, Thunderbird, every mobile
    calendar app imports it. UID is the event's stable ``id``,
    so re-importing after an organiser edit updates the existing
    entry instead of creating a duplicate."""
    event = _resolve_event(db, slug)
    ics = build_event_ics(event, public_base_url=PUBLIC_BASE_URL)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8; method=PUBLISH",
        headers={
            "Content-Disposition": f'attachment; filename="event-{event.slug}.ics"',
            "Cache-Control": "public, max-age=300",
        },
    )


@lru_cache(maxsize=256)
def _render_qr(slug: str) -> bytes:
    """Generate the QR SVG for one slug. SVG-path rendering is
    pure-Python (no PIL), produces ~1–2 KB of markup that scales
    losslessly, and is transparent by default — dark modules are
    ``<path>`` elements, the background is empty, so the QR sits
    on whatever surface composites it.

    Per-process LRU keeps repeat fetches at memory speed; 256
    entries caps roughly N events per worker, any organiser with
    that many events has bigger concerns."""
    target = f"{PUBLIC_BASE_URL}/e/{slug}"
    qr = qrcode.QRCode(box_size=10, border=2, image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(target)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    return buf.getvalue()


@router.get("/by-slug/{slug}/qr.svg")
def get_event_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    event = _resolve_event(db, slug)
    return Response(
        content=_render_qr(event.slug),
        media_type="image/svg+xml",
        # Browser-side cache complements the in-process LRU: 24h
        # turns repeat dashboard visits into 304 Not Modified.
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/by-slug/{slug}/feedback-preview")
def feedback_form_preview(slug: str, db: Session = Depends(get_db)) -> FeedbackFormOut:
    """Preview of the post-event feedback form."""
    event = _resolve_event(db, slug)
    if not event.feedback_enabled:
        raise HTTPException(status_code=404, detail="Channel disabled")

    return FeedbackFormOut(
        event_name=event.name,
        event_slug=event.slug,
        event_locale=event.locale,
        questions=[
            FeedbackQuestionOut(key=q.key, ordinal=q.ordinal, kind=q.kind, required=q.required) for q in QUESTIONS
        ],
    )


@router.get("/by-slug/{slug}/email-preview/{channel}")
def email_preview(slug: str, channel: str, db: Session = Depends(get_db)) -> Response:
    """Render the exact email that the dispatcher will send to a
    signup on this event."""
    event = _resolve_event(db, slug)
    ch = _resolve_channel(channel)

    if not mail_lifecycle.channel_enabled_for(ch, event):
        raise HTTPException(status_code=404, detail="Channel disabled")
    cdef = mail_lifecycle.CHANNELS[ch]
    context = dict(cdef.context(event))
    if ch == EmailChannel.FEEDBACK:
        context["feedback_url"] = build_url(f"e/{event.slug}/feedback", t="preview")

    _, html_body = render(cdef.template, context, locale=event.locale)
    return Response(content=html_body, media_type="text/html; charset=utf-8")
