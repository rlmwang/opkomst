"""Public, unauthenticated chapter reads.

Just the agenda for now: the per-chapter list of upcoming + recent-past
events behind ``/e/{chapter}``. Mounted before the organiser
``chapters`` router so the ``/by-slug/{slug}`` path wins over any
``/{chapter_id}`` match.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.agenda import ChapterAgendaOut
from ..services import agenda as agenda_svc
from ..services import chapters as chapters_svc

router = APIRouter(prefix="/api/v1/chapters", tags=["chapters-public"])


@router.get("/by-slug/{slug}/agenda", response_model=ChapterAgendaOut)
def chapter_agenda(slug: str, response: Response, db: Session = Depends(get_db)) -> ChapterAgendaOut:
    chapter = chapters_svc.find_live_by_slug(db, slug)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
    return agenda_svc.build_agenda(db, chapter)
