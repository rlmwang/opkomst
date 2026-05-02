"""Serve the Vue SPA in production.

The Vite build is copied to ``frontend/dist`` by the Dockerfile.
The hashed ``assets/`` directory mounts with a 1-year ``immutable``
``Cache-Control`` header (filenames are content-hashed by Vite, so
a changed file ships under a new URL).

Two HTML entry points:

* ``/e/{slug}`` — the public sign-up mini-app (``public-event.html``).
  The handler looks the event up server-side and injects the
  payload into the HTML as ``window.__OPKOMST_EVENT__`` so the
  Vue mini-app has data on first paint, no API round-trip needed.
* every other non-/api path — the admin SPA (``index.html``); the
  client-side router takes it from there.

Locally (``frontend/dist`` absent) ``mount(app)`` is a no-op, so
``uvicorn --reload`` against a fresh checkout doesn't 500 on
missing files.
"""

import html
import json
import pathlib
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.types import Scope

from ..config import settings
from ..database import get_db
from ..models import Event
from ..services import event_stats
from ..services import events as events_svc

_DIST = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

_IMMUTABLE = "public, max-age=31536000, immutable"

# Slug shape — 8 nanoid chars (see ``backend/services/slug.py``).
# The strict shape doubles as an injection guard: only requests
# matching this regex are looked up server-side.
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

# Markers the public HTML uses to receive the inlined payload
# and the per-event ``<head>`` metadata (title + Open Graph +
# Twitter Card tags). Anchored to unique strings so we don't
# accidentally substitute in the SPA's own ``index.html`` if it
# ever grows the same shape.
_INJECTION_MARKER = "<!-- OPKOMST_EVENT_INJECTION -->"
_HEAD_INJECTION_MARKER = "<!-- OPKOMST_HEAD_INJECTION -->"

_PUBLIC_BASE = str(settings.public_base_url).rstrip("/")
# Static OG image — same favicon the browser tab uses, lives at
# the SPA root. WhatsApp/Telegram require an absolute URL with a
# valid extension; ``favicon.png`` is 192×192 which is above the
# 200×200 minimum most parsers want.
_OG_IMAGE_URL = f"{_PUBLIC_BASE}/favicon.png"


def _build_head_meta(event: Event | None, slug: str) -> str:
    """Per-event ``<head>`` markup: page title + Open Graph +
    Twitter Card tags. Drives the link-preview cards rendered by
    WhatsApp, Facebook, iMessage, Slack, Twitter, LinkedIn — all
    of which scrape ``og:title`` / ``og:description`` /
    ``og:image`` from the served HTML.

    For unknown slugs (event is None) only the bare site title
    is emitted; sharing a 404 link is rare enough that elaborate
    fallback metadata isn't worth the bytes."""
    if event is None:
        return "<title>opkomst.nu</title>"

    # Description: topic if the organiser set one (it's the
    # editorial summary they'd want shared); otherwise fall back
    # to "{location} · {date}" which is the next-most-useful at-
    # a-glance summary. Truncated to ~200 chars — Facebook caps
    # display around there and WhatsApp lower.
    if event.topic:
        description = event.topic
    else:
        description = f"{event.location} · {event.starts_at.strftime('%-d %b %Y')}"
    if len(description) > 200:
        description = description[:197] + "…"

    title = f"{event.name} — opkomst.nu"
    canonical_url = f"{_PUBLIC_BASE}/e/{slug}"

    # ``html.escape`` covers the HTML-attribute injection surface
    # (event names with quotes, ampersands, angle brackets).
    # ``quote=True`` is the default and is what we need for
    # values inside attributes.
    et = html.escape(title, quote=True)
    ed = html.escape(description, quote=True)
    eu = html.escape(canonical_url, quote=True)
    ei = html.escape(_OG_IMAGE_URL, quote=True)
    en = html.escape(event.name, quote=True)

    return (
        f"<title>{et}</title>\n"
        f'    <meta name="description" content="{ed}">\n'
        f'    <meta property="og:title" content="{en}">\n'
        f'    <meta property="og:description" content="{ed}">\n'
        f'    <meta property="og:type" content="website">\n'
        f'    <meta property="og:url" content="{eu}">\n'
        f'    <meta property="og:site_name" content="opkomst.nu">\n'
        f'    <meta property="og:image" content="{ei}">\n'
        f'    <meta name="twitter:card" content="summary">\n'
        f'    <meta name="twitter:title" content="{en}">\n'
        f'    <meta name="twitter:description" content="{ed}">\n'
        f'    <meta name="twitter:image" content="{ei}">'
    )


class _ImmutableStatic(StaticFiles):
    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _IMMUTABLE
        return response


def _serve_public_event(slug: str, db: Session) -> HTMLResponse:
    """Render ``public-event.html`` with the event payload inlined.

    Visitor flow without inlining: load HTML → parse JS → fetch
    event by slug → render. With inlining: load HTML (event data
    already in the response body) → parse JS → render. One round-
    trip eliminated; the form is interactive as soon as the JS
    parses.

    Response carries ``Cache-Control: public, s-maxage=60,
    stale-while-revalidate=300`` — same window the
    ``/api/v1/events/by-slug/{slug}`` JSON endpoint uses. The
    rendered HTML is identical for every visitor between two
    organiser edits, so a 60 s shared cache (Coolify/Traefik or
    any CDN that fronts the app) keeps the common case off the
    DB; ``stale-while-revalidate`` serves the warm payload after
    expiry while one background fetch refreshes. Trade-off: an
    organiser edit takes up to 60 s to surface to new visitors
    via the inlined data."""
    public_html_path = _DIST / "public-event.html"
    if not public_html_path.is_file():
        # Build artefact missing — fall back to the SPA shell so
        # at least the admin app loads, and let the client-side
        # router (if it ever picks up /e/:slug again) render
        # something sane.
        return HTMLResponse(
            (_DIST / "index.html").read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store"},
        )

    if _SLUG_RE.match(slug):
        event = events_svc.get_event_by_slug_any(db, slug)
        payload: object | None = (
            json.loads(event_stats.to_out(db, event).model_dump_json()) if event is not None else None
        )
    else:
        event = None
        payload = None

    inlined = "<script>window.__OPKOMST_EVENT__ = " + json.dumps(payload, ensure_ascii=False) + ";</script>"
    head_meta = _build_head_meta(event, slug)
    rendered = (
        public_html_path.read_text(encoding="utf-8")
        .replace(_HEAD_INJECTION_MARKER, head_meta, 1)
        .replace(_INJECTION_MARKER, inlined, 1)
    )
    # Cache the response. ``max-age`` is the browser cache;
    # ``s-maxage`` covers any shared cache that fronts us
    # (Coolify/Traefik or a future CDN); ``stale-while-revalidate``
    # serves the warm payload after expiry while one background
    # fetch refreshes. Without ``max-age`` the browser hits the
    # server on every reload — Coolify doesn't currently run a CDN
    # in front, so the shared-cache window alone bought nothing on
    # repeat reloads. Trade-off: an organiser edit takes up to 60 s
    # to surface to new visitors via the inlined data; acceptable
    # since edits during an active sign-up window are rare.
    return HTMLResponse(
        rendered,
        headers={"Cache-Control": "public, max-age=60, s-maxage=60, stale-while-revalidate=300"},
    )


def mount(app: FastAPI) -> None:
    if not _DIST.is_dir():
        return

    app.mount("/assets", _ImmutableStatic(directory=_DIST / "assets"), name="assets")
    dist_resolved = _DIST.resolve()

    @app.get("/e/{slug}", include_in_schema=False)
    def _public_event(slug: str, db: Session = Depends(get_db)) -> HTMLResponse:
        return _serve_public_event(slug, db)

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> FileResponse:
        # ``StaticFiles`` already won the route for ``/assets/*``
        # and the explicit ``/e/{slug}`` handler above wins for
        # the public mini-app; this handler covers everything
        # else. We serve ``index.html`` for unknown paths so the
        # admin client-side router can render its 404 page.
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404, detail="Not found")
        # Resolve the requested path and require it to live under
        # the dist directory; without this a request like
        # ``/../../etc/passwd`` would happily serve any readable
        # file off the host.
        candidate = (_DIST / full_path).resolve()
        try:
            candidate.relative_to(dist_resolved)
        except ValueError:
            return FileResponse(_DIST / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
