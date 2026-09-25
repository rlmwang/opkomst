"""The manual on the web (``docs/design-manual.md`` chapter 7).

Server-rendered with no bundle, like every page that is read rather
than used. One route family, four bases: the root in Dutch and in
English, and each organisation in both, in its own brand.

The language is the address, because a server page cannot read the
language the app keeps in the browser. The audience is the base: under
an organisation's prefix the organisation's chapters and paragraphs
are in; at the root they are not, so the root rendering never mentions
that an organisation version exists.

Advertising follows the written pages: a root chapter carries the slot
on the terms in ``docs/ads.md``, the index carries none because a list
of links is not content to put an ad beside, and an organisation's
manual carries none like every page in its brand. An organisation's
manual is also marked not to be indexed, like the rest of its pages.
"""

import pathlib

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..services import brand as brand_svc
from ..services import manual, traffic
from ..services import tenants as tenants_svc
from ..services.manual import Audience

router = APIRouter(tags=["manual"], include_in_schema=False)

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
        "previous": "Vorige",
        "next": "Volgende",
        "twin": "English",
        "footer_label": "Meer lezen",
    },
    "en": {
        "manual": "Manual",
        "contents": "Contents",
        "download": "Download as PDF",
        "previous": "Previous",
        "next": "Next",
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


def _render(
    request: Request,
    *,
    word: str,
    tenant: str | None,
    db: Session,
    chapter: manual.Chapter | None,
) -> HTMLResponse:
    language = _WORDS[word]
    base, brand_slug, audience = _base_and_brand(db, tenant)
    chapters = manual.chapters_for(language, audience)
    house = brand_slug == brand_svc.HOUSE_BRAND
    traffic.record("content")

    # A root chapter carries the slot the written pages carry, and sets
    # the flag the security middleware reads. Nothing else here does.
    ads = brand_svc.payload(brand_svc.HOUSE_BRAND)["ads"] if house and chapter is not None else None
    ads = ads if ads and ads["client_id"] else None
    request.state.ads_allowed = ads is not None

    position = next((i for i, c in enumerate(chapters) if chapter is not None and c.slug == chapter.slug), None)
    previous = chapters[position - 1] if position not in (None, 0) else None
    following = chapters[position + 1] if position is not None and position + 1 < len(chapters) else None
    twin_slug = None
    if chapter is not None:
        # The same number in the other language, whatever its slug.
        twin = next(
            (c for c in manual.chapters_for(_WORDS[_TWIN[language]], audience) if c.number == chapter.number), None
        )
        twin_slug = twin.slug if twin else None

    path = f"{base}/{word}" + (f"/{chapter.slug}" if chapter else "")
    twin_path = f"{base}/{_TWIN[language]}" + (f"/{twin_slug}" if twin_slug else "")
    labels = _LABELS[language]
    title = chapter.title if chapter else labels["manual"]
    description = chapter.description if chapter else _INDEX_DESCRIPTION[language]

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
            "word": word,
            "path": path,
            "twin_path": twin_path,
            "chapters": chapters,
            "chapter": chapter,
            "body_html": chapter.html_for(audience) if chapter else None,
            "previous": previous,
            "following": following,
            "pdf_path": f"{base}/{word}.pdf",
            "page_title": title,
            "page_description": description,
            "canonical_url": f"{_PUBLIC_BASE}{path}",
            "noindex": not house,
            "ads": ads,
            "csp_nonce": request.state.csp_nonce,
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


_INDEX_DESCRIPTION = {
    "nl": "De handleiding: hoe je inlogt, een evenement maakt, de link deelt, en wat je doet als iets misgaat.",
    "en": "The manual: how to sign in, make an event, share the link, and what to do when something goes wrong.",
}


def _chapter(language: str, slug: str) -> manual.Chapter:
    chapter = manual.by_slug(language, slug)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Not found")
    return chapter


# Literal words, never a path parameter: ``/{word}`` in front of the SPA
# fallback would match every one-segment path in the app and answer
# ``/rsp`` and ``/event`` with a 404 of its own.
for _word in _WORDS:

    def _root_index(request: Request, db: Session = Depends(get_db), _w: str = _word) -> HTMLResponse:
        return _render(request, word=_w, tenant=None, db=db, chapter=None)

    def _root_chapter(slug: str, request: Request, db: Session = Depends(get_db), _w: str = _word) -> HTMLResponse:
        chapter = _chapter(_WORDS[_w], slug)
        if chapter.audience != "all":
            raise HTTPException(status_code=404, detail="Not found")
        return _render(request, word=_w, tenant=None, db=db, chapter=chapter)

    def _tenant_index(tenant: str, request: Request, db: Session = Depends(get_db), _w: str = _word) -> HTMLResponse:
        return _render(request, word=_w, tenant=tenant, db=db, chapter=None)

    def _tenant_chapter(
        tenant: str, slug: str, request: Request, db: Session = Depends(get_db), _w: str = _word
    ) -> HTMLResponse:
        return _render(request, word=_w, tenant=tenant, db=db, chapter=_chapter(_WORDS[_w], slug))

    for _path, _handler in (
        (f"/{_word}", _root_index),
        (f"/{_word}/{{slug}}", _root_chapter),
        (f"/{{tenant}}/{_word}", _tenant_index),
        (f"/{{tenant}}/{_word}/{{slug}}", _tenant_chapter),
    ):
        router.add_api_route(_path, _handler, methods=["GET", "HEAD"], response_class=HTMLResponse)


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
