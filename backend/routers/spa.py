"""Serve the Vue SPA in production.

The Vite build is copied to ``frontend/dist`` by the Dockerfile.
The hashed ``assets/`` directory mounts with a 1-year ``immutable``
``Cache-Control`` header (filenames are content-hashed by Vite, so
a changed file ships under a new URL).

Entry points:

* ``/e/{slug}``, ``/f/{slug}``, ``/d/{slug}``, ``/c/{slug}`` and
  ``/e/{chapter}`` — the public mini-apps. Each handler resolves its
  entity server-side and injects the payload into the HTML (as
  ``window.__OPKOMST_EVENT__`` and friends) so the page is interactive
  on first paint, plus the per-page ``<head>`` metadata for link
  previews. These URLs carry no tenant: the entity behind the slug is
  what decides whose brand the page wears.
* ``/{tenant}/…`` — an organisation's organiser SPA (``index.html``),
  for every live organisation slug.
* everything else — the same SPA in the house brand, based at ``/``:
  the personal app, where an address is the account. Its own router
  renders the not-found page for paths it doesn't know.
* ``/brand/{tenant}/…`` — the brand files (palette, logo, icons),
  served from ``brands/`` whether or not a frontend build exists.

Locally (``frontend/dist`` absent) everything but the brand mount is
skipped, so ``uvicorn --reload`` against a fresh checkout doesn't 500 on
missing files.
"""

import html
import json
import pathlib
import re
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.types import Scope

from ..config import settings
from ..database import get_db
from ..models import Chapter, Datepoll, Form, Occurrence, Roster
from ..schemas.common import pick_localized
from ..services import agenda as agenda_svc
from ..services import brand as brand_svc
from ..services import chapters as chapters_svc
from ..services import chores as chores_svc
from ..services import datepolls as datepolls_svc
from ..services import events as events_svc
from ..services import forms as forms_svc
from ..services import image as image_svc
from ..services import tenancy
from ..services import tenants as tenants_svc
from ..services.sanitize import html_to_text

_DIST = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

_IMMUTABLE = "public, max-age=31536000, immutable"
_BRAND_CACHE = "public, max-age=3600"

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
# Distinct payload marker for the form mini-app — the head-meta
# marker is shared (same ``<!-- OPKOMST_HEAD_INJECTION -->``)
# because the per-page head metadata serves the same role on both
# pages.
_FORM_INJECTION_MARKER = "<!-- OPKOMST_FORM_INJECTION -->"
_DATEPOLL_INJECTION_MARKER = "<!-- OPKOMST_DATEPOLL_INJECTION -->"
_CHORE_INJECTION_MARKER = "<!-- OPKOMST_CHORE_INJECTION -->"
_CHAPTER_INJECTION_MARKER = "<!-- OPKOMST_CHAPTER_INJECTION -->"
# The brand marker every shell carries, admin SPA included: palette
# stylesheet, icons, first-paint colours, ``window.__OPKOMST_BRAND__``.
_BRAND_INJECTION_MARKER = "<!-- OPKOMST_BRAND_INJECTION -->"

_PUBLIC_BASE = str(settings.public_base_url).rstrip("/")


def _og_head(*, name: str, description: str, canonical_url: str, image_url: str | None, brand_slug: str) -> str:
    """Shared ``<head>`` markup: page title + Open Graph + Twitter
    Card tags. Drives the link-preview cards rendered by WhatsApp,
    Facebook, iMessage, Slack, Twitter, LinkedIn — all of which
    scrape ``og:title`` / ``og:description`` / ``og:image`` from
    the served HTML. ``html.escape(..., quote=True)`` covers the
    HTML-attribute injection surface (names with quotes, ampersands,
    angle brackets).

    ``image_url`` is the entity's uploaded hero image (every
    ``OrgEntity`` — event / datepoll / roster / form — carries one on
    its spine), or ``None`` for surfaces without an image. A real
    upload gets the large-image card; the ``None`` fallback shows the
    owning organisation's square favicon under the tiny ``summary``
    thumbnail (the house brand has none, so that card has no image).

    The site name and the title suffix are the owning organisation's
    too — a shared link says whose event it is, not which tool made
    the page."""
    brand = brand_svc.payload(brand_slug)
    app_name = brand["app_name"]
    og_image = image_url or brand["favicon_absolute_url"]
    twitter_card = "summary_large_image" if image_url else "summary"
    et = html.escape(f"{name} · {app_name}", quote=True)
    ed = html.escape(description, quote=True)
    eu = html.escape(canonical_url, quote=True)
    en = html.escape(name, quote=True)
    tags = [
        f"<title>{et}</title>",
        f'<meta name="description" content="{ed}">',
        f'<meta property="og:title" content="{en}">',
        f'<meta property="og:description" content="{ed}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{eu}">',
        f'<meta property="og:site_name" content="{html.escape(app_name, quote=True)}">',
        f'<meta name="twitter:card" content="{twitter_card}">',
        f'<meta name="twitter:title" content="{en}">',
        f'<meta name="twitter:description" content="{ed}">',
    ]
    if og_image:
        ei = html.escape(og_image, quote=True)
        tags.append(f'<meta property="og:image" content="{ei}">')
        tags.append(f'<meta name="twitter:image" content="{ei}">')
    return "\n    ".join(tags)


def _build_head_meta(occurrence: Occurrence | None, slug: str, brand_slug: str) -> str:
    """Per-occurrence link-preview ``<head>`` (the public page is per
    occurrence). For unknown slugs (occurrence is None) only the bare site
    title is emitted; sharing a 404 link is rare enough that elaborate
    fallback metadata isn't worth the bytes."""
    if occurrence is None:
        return f"<title>{brand_svc.payload(brand_slug)['app_name']}</title>"
    event = occurrence.event

    # Description: topic if the organiser set one (it's the
    # editorial summary they'd want shared); otherwise fall back
    # to "{location} · {date}" which is the next-most-useful at-
    # a-glance summary. Truncated to ~200 chars — Facebook caps
    # display around there and WhatsApp lower.
    # ``topic`` is sanitized rich-text HTML; flatten it to plain text
    # before it lands in a ``<meta>`` attribute (tags would otherwise
    # show up literally in link previews).
    topic_text = html_to_text(pick_localized(event.topic_nl, event.topic_en, event.locale))
    if topic_text:
        description = topic_text
    else:
        when = occurrence.starts_at.strftime("%-d %b %Y")
        description = f"{event.location} · {when}" if event.location else when
    if len(description) > 200:
        description = description[:197] + "…"

    return _og_head(
        name=pick_localized(event.name_nl, event.name_en, event.locale) or "",
        description=description,
        canonical_url=f"{_PUBLIC_BASE}/e/{slug}",
        image_url=image_svc.public_url(event.image_path),
        brand_slug=brand_slug,
    )


def _build_form_head_meta(form: Form | None, slug: str, brand_slug: str) -> str:
    """Per-form link-preview ``<head>``. Forms have no topic /
    location / date, so the description is just the form name; the
    card uses the organiser's uploaded image when set."""
    if form is None:
        return f"<title>{brand_svc.payload(brand_slug)['app_name']}</title>"
    form_name = pick_localized(form.name_nl, form.name_en, form.locale) or ""
    return _og_head(
        name=form_name,
        description=form_name,
        canonical_url=f"{_PUBLIC_BASE}/f/{slug}",
        image_url=image_svc.public_url(form.image_path),
        brand_slug=brand_slug,
    )


def _build_datepoll_head_meta(poll: Datepoll | None, slug: str, brand_slug: str) -> str:
    """Per-datepoll link-preview ``<head>``. Description is the poll's
    blurb if set, else its name; card uses the uploaded image when set."""
    if poll is None:
        return f"<title>{brand_svc.payload(brand_slug)['app_name']}</title>"
    poll_name = pick_localized(poll.name_nl, poll.name_en, poll.locale) or ""
    return _og_head(
        name=poll_name,
        description=html_to_text(pick_localized(poll.description_nl, poll.description_en, poll.locale)) or poll_name,
        canonical_url=f"{_PUBLIC_BASE}/d/{slug}",
        image_url=image_svc.public_url(poll.image_path),
        brand_slug=brand_slug,
    )


def _build_roster_head_meta(roster: Roster | None, slug: str, brand_slug: str) -> str:
    """Per-roster link-preview ``<head>``. Description is the roster's
    blurb if set, else its name; card uses the uploaded image when set."""
    if roster is None:
        return f"<title>{brand_svc.payload(brand_slug)['app_name']}</title>"
    roster_name = pick_localized(roster.name_nl, roster.name_en, roster.locale) or ""
    blurb = html_to_text(pick_localized(roster.description_nl, roster.description_en, roster.locale))
    return _og_head(
        name=roster_name,
        description=blurb or roster_name,
        canonical_url=f"{_PUBLIC_BASE}/c/{slug}",
        image_url=image_svc.public_url(roster.image_path),
        brand_slug=brand_slug,
    )


def _build_chapter_head_meta(chapter: Chapter | None, slug: str, brand_slug: str) -> str:
    """Per-chapter agenda link-preview ``<head>``. Title is
    ``Agenda · {name}``; a chapter has no image, so the favicon card."""
    if chapter is None:
        return f"<title>{brand_svc.payload(brand_slug)['app_name']}</title>"
    return _og_head(
        name=f"Agenda · {chapter.name}",
        description=chapter.name,
        canonical_url=f"{_PUBLIC_BASE}/e/{slug}",
        image_url=None,
        brand_slug=brand_slug,
    )


class _ImmutableStatic(StaticFiles):
    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _IMMUTABLE
        return response


class _BrandStatic(StaticFiles):
    """``brands/`` served at ``/brand/{tenant}/…``. Unlike the Vite
    assets these keep their filenames across edits, so they get an
    hour's caching rather than a year's immutability — a palette tweak
    reaches visitors the same day it deploys."""

    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _BRAND_CACHE
        return response


def _nonce(request: Request) -> str:
    """The per-response CSP nonce ``SecurityHeadersMiddleware`` minted
    for this request. Every inline script a shell carries has to wear
    it or the browser refuses to run it."""
    return request.state.csp_nonce


def _allow_ads(request: Request, brand_slug: str) -> None:
    """Say whether this response may carry advertising, for
    ``SecurityHeadersMiddleware`` to pick the CSP from (see
    ``docs/ads.md``).

    Two conditions, both required. Only pages no organisation owns may
    ever carry ads, and the brand the page wears is exactly that
    question, already answered. And only a deployment that has been
    given an ``ADSENSE_CLIENT_ID`` serves an ad script at all: without
    one the slot renders a committed image, no Google code loads, no
    consent dialog appears and no cookie is set, so there is nothing to
    open the policy for."""
    request.state.ads_allowed = brand_slug == brand_svc.HOUSE_BRAND and settings.adsense_client_id is not None


def _serve_admin_shell(tenant_slug: str, request: Request, *, status_code: int = 200) -> HTMLResponse:
    """The organiser SPA shell, wearing the brand of the organisation
    whose slug opened the URL. Served for every path under a live
    tenant so the client-side router can take over; the injected brand
    carries the base the router mounts at.

    Also serves the not-found page: a path no organisation owns gets
    the same shell in the house brand with ``status_code=404``, so the
    visitor sees the app's own 404 rather than a bare error string.

    ``index.html`` MUST NOT be browser-cached — see the note in
    ``_spa_fallback``."""
    _allow_ads(request, tenant_slug)
    rendered = (
        (_DIST / "index.html")
        .read_text(encoding="utf-8")
        .replace(_BRAND_INJECTION_MARKER, brand_svc.head(tenant_slug, _nonce(request)), 1)
    )
    return HTMLResponse(rendered, status_code=status_code, headers={"Cache-Control": "no-store"})


def _serve_public_app(
    *,
    html_name: str,
    window_var: str,
    payload_marker: str,
    payload: object | None,
    head_meta: str,
    brand_slug: str,
    request: Request,
) -> HTMLResponse:
    """Render one public mini-app shell with its payload inlined.

    The three public surfaces (event sign-up, form, datepoll) share
    this body: load the prebuilt HTML, inject the per-page ``<head>``
    metadata + the JSON payload (so the page is interactive on first
    paint, no API round-trip), and serve it with the 60 s
    ``stale-while-revalidate`` window. The rendered HTML is identical
    for every visitor between two organiser edits, so a shared cache
    (Coolify/Traefik or a future CDN) keeps the common case off the
    DB; the trade-off is that an organiser edit takes up to 60 s to
    surface to new visitors via the inlined data.

    Each caller resolves its own entity and decides the archived
    policy (events inline the archived event's payload to render a
    banner; forms/datepolls inline ``null`` so the mini-app shows
    "no longer available"), and passes the brand of the organisation
    that owns it — the URL carries no tenant, so the entity is what
    decides whose logo and palette the visitor sees. An unknown slug
    has no owner and gets the house brand. When the build artefact is
    missing (local dev without a frontend build) we fall back to the
    organiser shell, uncached."""
    public_html_path = _DIST / html_name
    if not public_html_path.is_file():
        return _serve_admin_shell(brand_slug, request)
    _allow_ads(request, brand_slug)
    nonce = _nonce(request)
    inlined = f'<script nonce="{nonce}">window.{window_var} = ' + json.dumps(payload, ensure_ascii=False) + ";</script>"
    rendered = (
        public_html_path.read_text(encoding="utf-8")
        .replace(_BRAND_INJECTION_MARKER, brand_svc.head(brand_slug, nonce), 1)
        .replace(_HEAD_INJECTION_MARKER, head_meta, 1)
        .replace(payload_marker, inlined, 1)
    )
    return HTMLResponse(
        rendered,
        headers={"Cache-Control": "public, max-age=60, s-maxage=60, stale-while-revalidate=300"},
    )


# The four tenant-free public URL prefixes, each with the resolver that
# turns its slug back into the entity that owns it. ``brand_slug_for``
# is the one question a caller outside this module asks of it.
_PUBLIC_RESOLVERS: dict[str, Callable[[Session, str], Any]] = {
    "e": events_svc.get_occurrence_by_slug_any,
    "f": forms_svc.get_form_by_slug_any,
    "d": datepolls_svc.get_datepoll_by_slug_any,
    "c": chores_svc.get_roster_by_slug_any,
}

_Entity = TypeVar("_Entity")


def _resolve_public(db: Session, slug: str, resolve: Callable[[Session, str], _Entity | None]) -> _Entity | None:
    """The entity behind a tenant-free public URL, or ``None`` when the
    slug names nothing. One guard in one place: a malformed slug never
    reaches the database."""
    return resolve(db, slug) if _SLUG_RE.match(slug) else None


def brand_slug_for(db: Session, prefix: str, slug: str) -> str:
    """Which brand ``/{prefix}/{slug}`` wears. The Vite dev server asks
    this because it has no database of its own and would otherwise have
    to guess."""
    resolve = _PUBLIC_RESOLVERS.get(prefix)
    entity = _resolve_public(db, slug, resolve) if resolve is not None else None
    return _brand_slug_for(db, entity)


def _brand_slug_for(db: Session, entity: object | None) -> str:
    """Which brand a public page wears: the one belonging to the tenant
    that owns the entity behind the slug. An unknown or archived slug
    resolved to nothing, so there is no owner to ask, and those pages
    wear the house brand. So does a personal account's page: its slug
    names no brand folder, which is what ``brand_slug`` decides."""
    if entity is None:
        return brand_svc.HOUSE_BRAND
    tenant = tenants_svc.get_live(db, entity.tenant_id)  # type: ignore[attr-defined]
    return tenant.brand_slug if tenant is not None else brand_svc.HOUSE_BRAND


def _serve_public_event(slug: str, db: Session, request: Request) -> HTMLResponse:
    # Events render archived events with a banner, so inline the
    # archived event's payload (allow_archived) rather than null.
    occurrence = _resolve_public(db, slug, events_svc.get_occurrence_by_slug_any)
    payload = (
        json.loads(events_svc.build_public_event(db, occurrence).model_dump_json()) if occurrence is not None else None
    )
    brand_slug = _brand_slug_for(db, occurrence)
    return _serve_public_app(
        html_name="public-event.html",
        window_var="__OPKOMST_EVENT__",
        payload_marker=_INJECTION_MARKER,
        payload=payload,
        head_meta=_build_head_meta(occurrence, slug, brand_slug),
        brand_slug=brand_slug,
        request=request,
    )


def _serve_public_form(slug: str, db: Session, request: Request) -> HTMLResponse:
    # Archived/unknown forms inline null; the mini-app shows the same
    # "no longer available" state it would on a 410.
    form = _resolve_public(db, slug, forms_svc.get_form_by_slug_any)
    payload = json.loads(forms_svc.to_public_out(db, form).model_dump_json()) if form is not None else None
    brand_slug = _brand_slug_for(db, form)
    return _serve_public_app(
        html_name="public-form.html",
        window_var="__OPKOMST_FORM__",
        payload_marker=_FORM_INJECTION_MARKER,
        payload=payload,
        head_meta=_build_form_head_meta(form, slug, brand_slug),
        brand_slug=brand_slug,
        request=request,
    )


def _serve_public_datepoll(slug: str, db: Session, request: Request) -> HTMLResponse:
    # Archived/unknown polls inline null, same as forms.
    poll = _resolve_public(db, slug, datepolls_svc.get_datepoll_by_slug_any)
    payload = json.loads(datepolls_svc.to_public_out(db, poll).model_dump_json()) if poll is not None else None
    brand_slug = _brand_slug_for(db, poll)
    return _serve_public_app(
        html_name="public-datepoll.html",
        window_var="__OPKOMST_DATEPOLL__",
        payload_marker=_DATEPOLL_INJECTION_MARKER,
        payload=payload,
        head_meta=_build_datepoll_head_meta(poll, slug, brand_slug),
        brand_slug=brand_slug,
        request=request,
    )


def _serve_public_roster(slug: str, db: Session, request: Request) -> HTMLResponse:
    # Archived/unknown rosters inline null, same as forms/datepolls.
    roster = _resolve_public(db, slug, chores_svc.get_roster_by_slug_any)
    payload = json.loads(chores_svc.to_public_out(db, roster).model_dump_json()) if roster is not None else None
    brand_slug = _brand_slug_for(db, roster)
    return _serve_public_app(
        html_name="public-chore.html",
        window_var="__OPKOMST_CHORE__",
        payload_marker=_CHORE_INJECTION_MARKER,
        payload=payload,
        head_meta=_build_roster_head_meta(roster, slug, brand_slug),
        brand_slug=brand_slug,
        request=request,
    )


def _serve_public_chapter(chapter: Chapter, slug: str, db: Session, request: Request, brand_slug: str) -> HTMLResponse:
    """The organisation's agenda for one of its chapters, at
    ``/{tenant}/{chapter}``. The caller has already resolved both — the
    tenant from the first path segment, the chapter within it — so the
    brand is the tenant's, not a lookup through the entity."""
    payload = json.loads(agenda_svc.build_agenda(db, chapter).model_dump_json())
    return _serve_public_app(
        html_name="public-chapter.html",
        window_var="__OPKOMST_CHAPTER__",
        payload_marker=_CHAPTER_INJECTION_MARKER,
        payload=payload,
        head_meta=_build_chapter_head_meta(chapter, slug, brand_slug),
        brand_slug=brand_slug,
        request=request,
    )


def mount(app: FastAPI) -> None:
    # The brand files are served whether or not a frontend build exists:
    # in dev the Vite server proxies ``/brand`` here, and the mini-apps
    # need the logo from the same place prod serves it.
    app.mount("/brand", _BrandStatic(directory=brand_svc.BRANDS_DIR), name="brand")

    if not _DIST.is_dir():
        return

    app.mount("/assets", _ImmutableStatic(directory=_DIST / "assets"), name="assets")

    @app.get("/e/{slug}", include_in_schema=False)
    def _public_event(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        return _serve_public_event(slug, db, request)

    @app.get("/f/{slug}", include_in_schema=False)
    def _public_form(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        return _serve_public_form(slug, db, request)

    @app.get("/d/{slug}", include_in_schema=False)
    def _public_datepoll(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        return _serve_public_datepoll(slug, db, request)

    @app.get("/c/{slug}", include_in_schema=False)
    def _public_roster(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        return _serve_public_roster(slug, db, request)

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str, request: Request, db: Session = Depends(get_db)) -> Response:
        # ``StaticFiles`` already won the route for ``/assets/*`` and
        # ``/brand/*``, and the explicit public handlers above won for
        # the per-entity mini-apps. What's left lives under an
        # organisation's slug, and is one of two things:
        #
        #   /rsp/utrecht  → that chapter's public agenda
        #   /rsp/…        → the organiser app
        #
        # A chapter and a workspace share this namespace, which is why
        # ``services.slug.RESERVED_SLUGS`` keeps a chapter from being
        # called "events". A first segment that isn't a live
        # organisation belongs to the personal app at the root.
        #
        # ``index.html`` MUST NOT be browser-cached. Vite emits
        # content-hashed asset names (``main-AbCd1234.js``) which
        # the immutable mount above caches for a year; the manifest
        # in ``index.html`` is the only thing pinning a session to
        # a specific build. If a browser keeps a stale ``index.html``
        # after a redeploy, every chunk lookup 404s and the SPA
        # crashes with "disallowed MIME type" because FastAPI's
        # 404 body is JSON. ``no-store`` keeps the manifest fresh
        # on every navigation; the immutable assets keep loads
        # fast on warm visits.
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404, detail="Not found")
        tenant_slug = full_path.split("/", 1)[0]
        tenant = tenants_svc.find_live_organisation_by_slug(db, tenant_slug) if tenant_slug else None
        if tenant is None:
            # No organisation owns this path, so it belongs to the app
            # itself: the personal side, in the house brand, based at
            # ``/``. Its router resolves ``/events``, ``/login`` and the
            # rest, and renders its own not-found page for anything it
            # doesn't know — which is why this is a 200 and not a 404.
            return _serve_admin_shell(brand_svc.HOUSE_BRAND, request)

        # Inside the organisation now, so chapter reads are scoped to it.
        tenancy.bind(tenant.id, tenant.brand_slug)
        _, _, rest = full_path.partition("/")
        second = rest.split("/", 1)[0]
        chapter = chapters_svc.find_live_by_slug(db, second) if second else None
        if chapter is not None:
            return _serve_public_chapter(chapter, second, db, request, tenant.slug)
        return _serve_admin_shell(tenant.slug, request)
