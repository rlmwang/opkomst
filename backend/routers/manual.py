"""The manual on the web (``docs/design-manual.md`` chapter 7).

Server-rendered with no bundle, like every page that is read rather
than used. One page per base, four bases: the root in Dutch and in
English, and each organisation in both, in its own brand. The page is
the whole book: every chapter under its own anchor, the contents
column jumping to them, the PDF link at the top.

The language is the address, because a server page cannot read the
language the app keeps in the browser. The audience is the base: under
an organisation's prefix the organisation's chapters and paragraphs
are in; at the root they are not, so the root rendering never mentions
that an organisation version exists.

Advertising follows the written pages: the root's page carries the
slot on the terms in ``docs/ads.md``, and an organisation's carries
none like every page in its brand. An organisation's manual is also
marked not to be indexed, like the rest of its pages.
"""

import datetime
import pathlib
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..services import brand as brand_svc
from ..services import manual, traffic
from ..services import tenants as tenants_svc
from ..services.manual import Audience

router = APIRouter(tags=["manual"], include_in_schema=False)
logger = structlog.get_logger()

_TEMPLATES = Jinja2Templates(directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates"))
_PUBLIC_BASE = str(settings.public_base_url).rstrip("/")

# The word in the address is the language.
_WORDS: dict[str, str] = {"handleiding": "nl", "manual": "en"}
_TWIN: dict[str, str] = {"nl": "manual", "en": "handleiding"}
_LABELS: dict[str, dict[str, str]] = {
    "nl": {
        "manual": "Handleiding",
        "contents": "Inhoud",
        "download": "Download als PDF",
        "twin": "English",
        "footer_label": "Meer lezen",
    },
    "en": {
        "manual": "Manual",
        "contents": "Contents",
        "download": "Download as PDF",
        "twin": "Nederlands",
        "footer_label": "Read more",
    },
}


def _base_and_brand(db: Session, tenant: str | None) -> tuple[str, str, Audience]:
    """The address prefix, the brand folder and the audience for a base.
    An unknown or personal slug under a prefix is not a base."""
    if tenant is None:
        return "", brand_svc.HOUSE_BRAND, "all"
    row = tenants_svc.find_live_organisation_by_slug(db, tenant)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return f"/{tenant}", row.brand_slug, "organisation"


def _render(request: Request, *, word: str, tenant: str | None, db: Session) -> HTMLResponse:
    """The manual as one page: every chapter for the base's audience,
    stacked, each under its own anchor, with the contents column
    jumping to them and the PDF link at the top."""
    language = _WORDS[word]
    base, brand_slug, audience = _base_and_brand(db, tenant)
    chapters = manual.chapters_for(language, audience)
    house = brand_slug == brand_svc.HOUSE_BRAND
    traffic.record("content")

    # The root's manual is a house-brand page of prose, so it carries the
    # slot the written pages carry and sets the flag the security
    # middleware reads. An organisation's carries none.
    ads = brand_svc.payload(brand_svc.HOUSE_BRAND)["ads"] if house else None
    ads = ads if ads and ads["client_id"] else None
    request.state.ads_allowed = ads is not None

    path = f"{base}/{word}"
    labels = _LABELS[language]
    return _TEMPLATES.TemplateResponse(
        request,
        "manual.html",
        {
            "brand": brand_svc.payload(brand_slug),
            "palette_css": brand_svc.palette_css(brand_slug),
            "language": language,
            "labels": labels,
            "house": house,
            "base": base,
            "path": path,
            "twin_path": f"{base}/{_TWIN[language]}",
            # The chapter's own headings step down one level, because the
            # page has one title and fourteen chapters under it.
            "chapters": [(c, _demote(c.html_for(audience))) for c in chapters],
            "pdf_path": f"{base}/{word}.pdf",
            "page_title": labels["manual"],
            "page_description": _INDEX_DESCRIPTION[language],
            "canonical_url": f"{_PUBLIC_BASE}{path}",
            "noindex": not house,
            "ads": ads,
            "csp_nonce": request.state.csp_nonce,
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


_HEADING = re.compile(r"<(/?)h([23])\b")


def _demote(html: str) -> str:
    """``h2`` to ``h3`` and ``h3`` to ``h4``, so a chapter's sections sit
    under the chapter's own ``h2`` on the one page."""
    return _HEADING.sub(lambda m: f"<{m.group(1)}h{int(m.group(2)) + 1}", html)


_INDEX_DESCRIPTION = {
    "nl": "De handleiding: hoe je inlogt, een evenement maakt, de link deelt, en wat je doet als iets misgaat.",
    "en": "The manual: how to sign in, make an event, share the link, and what to do when something goes wrong.",
}


# Literal words, never a path parameter: ``/{word}`` in front of the SPA
# fallback would match every one-segment path in the app and answer
# ``/rsp`` and ``/event`` with a 404 of its own.
for _word in _WORDS:

    def _root(request: Request, db: Session = Depends(get_db), _w: str = _word) -> HTMLResponse:
        return _render(request, word=_w, tenant=None, db=db)

    def _tenant(tenant: str, request: Request, db: Session = Depends(get_db), _w: str = _word) -> HTMLResponse:
        return _render(request, word=_w, tenant=tenant, db=db)

    router.add_api_route(f"/{_word}", _root, methods=["GET", "HEAD"], response_class=HTMLResponse)
    router.add_api_route(f"/{{tenant}}/{_word}", _tenant, methods=["GET", "HEAD"], response_class=HTMLResponse)


# The PDFs the image build wrote (``backend/manual_pdf.py``), next to
# the bundle. Literal paths again. Nothing in local mode without a
# build, and that is a 404 rather than a render: Pango belongs in the
# build stage and not in the request path.
_PDF_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist" / "manual"


def _pdf(brand_slug: str, word: str) -> Response:
    path = _PDF_DIR / brand_slug / f"{word}.pdf"
    if path.is_file():
        return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "public, max-age=86400"})
    # A dev checkout has no build. In local mode the file is rendered on
    # request instead, which is the one place Pango is allowed in the
    # request path; without WeasyPrint installed the link is a 404 and
    # the log says why.
    if not settings.local_mode:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        from .. import manual_pdf
    except ImportError:
        logger.info("manual_pdf_unavailable", reason="weasyprint not installed; uv sync --group manual")
        raise HTTPException(status_code=404, detail="Not found") from None
    pdf = manual_pdf.render(brand_slug, _WORDS[word], datetime.date.today())
    return Response(pdf, media_type="application/pdf")


for _word in _WORDS:

    def _root_pdf(_w: str = _word) -> Response:
        return _pdf(brand_svc.HOUSE_BRAND, _w)

    def _tenant_pdf(tenant: str, db: Session = Depends(get_db), _w: str = _word) -> Response:
        _, brand_slug, _ = _base_and_brand(db, tenant)
        return _pdf(brand_slug, _w)

    router.add_api_route(f"/{_word}.pdf", _root_pdf, methods=["GET", "HEAD"], response_class=Response)
    router.add_api_route(f"/{{tenant}}/{_word}.pdf", _tenant_pdf, methods=["GET", "HEAD"], response_class=Response)


@router.api_route("/manual-pictures/{language}/{name}.png", methods=["GET", "HEAD"])
def picture(language: str, name: str) -> FileResponse:
    """A committed picture, cached the way the built assets are: it
    changes only with a deploy."""
    if language not in manual.LANGUAGES or "/" in name or ".." in name:
        raise HTTPException(status_code=404, detail="Not found")
    path = manual.picture_path(language, name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
