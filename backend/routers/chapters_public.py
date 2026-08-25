"""Public, unauthenticated reads about an organisation.

Two of them, both keyed by the organisation's slug because these URLs
carry it: the list of its chapters (its public front page, at
``/{tenant}``) and one chapter's agenda (at ``/{tenant}/{chapter}``).

The HTML for both is served with its payload already inlined
(``routers/spa.py``); these endpoints are what the pages fall back to
when there is no inlined payload — the dev server, and a client-side
navigation.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.agenda import ChapterAgendaOut
from ..schemas.chapters import ChapterPublicOut
from ..services import agenda as agenda_svc
from ..services import chapters as chapters_svc
from ..services import tenancy
from ..services import tenants as tenants_svc

router = APIRouter(prefix="/api/v1/tenants", tags=["public"])

_CACHE = "public, s-maxage=60, stale-while-revalidate=300"


def _bind_tenant(db: Session, tenant_slug: str) -> None:
    """Resolve the organisation in the URL and scope the request to it.
    An unknown slug is a 404, the same answer as a chapter that doesn't
    exist, so the surface doesn't enumerate organisations.

    Organisations only. A personal tenant's slug never appears in a URL,
    and the HTML route at the same path says the same thing; answering
    here would make this API an oracle for which generated slugs exist."""
    tenant = tenants_svc.find_live_organisation_by_slug(db, tenant_slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not found")
    tenancy.bind(tenant.id, tenant.brand_slug)


@router.get("/{tenant_slug}/chapters", response_model=list[ChapterPublicOut])
def tenant_chapters(tenant_slug: str, response: Response, db: Session = Depends(get_db)) -> list[ChapterPublicOut]:
    """The organisation's live chapters, for its public front page."""
    _bind_tenant(db, tenant_slug)
    response.headers["Cache-Control"] = _CACHE
    return [ChapterPublicOut.model_validate(c) for c in chapters_svc.all_active(db)]


@router.get("/{tenant_slug}/agenda/{slug}", response_model=ChapterAgendaOut)
def chapter_agenda(tenant_slug: str, slug: str, response: Response, db: Session = Depends(get_db)) -> ChapterAgendaOut:
    _bind_tenant(db, tenant_slug)
    chapter = chapters_svc.find_live_by_slug(db, slug)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    response.headers["Cache-Control"] = _CACHE
    return agenda_svc.build_agenda(db, chapter)
