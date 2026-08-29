"""Starting something without an account.

Six public endpoints — ``POST /api/v1/start/{events,forms,quizzes,
compasses,datepolls,chores}`` — that take an address plus the same body
an organiser posts,
and do three things in one transaction:

1. **Resolve the account.** A live personal user with that address owns
   the write; otherwise a personal tenant and its one user are created
   right here.
2. **Bind and write.** The tenant is bound and the entity goes through
   the same ``services.entities`` call the organiser route makes — one
   create path per kind, reached by two doors.
3. **Mail the link.** A single-use ``LoginToken``, in the house brand,
   naming what was made and the account it landed in.

The owner is decided by an address nobody has proved they control, and
that is deliberate: proving it is what the mail does, and the only thing
an unproven address buys is a row in an inbox you cannot read. The cost
is that a stranger who types someone else's address adds an entity to
their account — the mail makes that visible on arrival, and the rate
limit keeps it from being done in bulk.

The response says nothing about whether the account already existed.
"""

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas.start import (
    StartCompass,
    StartDatepoll,
    StartedOut,
    StartEvent,
    StartForm,
    StartQuiz,
    StartRoster,
)
from ..services import access, entities, event_stats, limits, tenancy
from ..services import tenants as tenants_svc
from ..services.mail import build_url, send_email
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/start", tags=["start"])

_PUBLIC_BASE = str(settings.public_base_url).rstrip("/")

# The public path each kind's slug lives under. What the mail *calls*
# each kind is in the templates, one set of words per language, because
# that is what a translation is.
_PREFIXES = {"event": "e", "form": "f", "datepoll": "d", "roster": "c", "quiz": "q", "compass": "k"}


def _resolve_account(db: Session, email: str) -> User:
    """The personal account for this address, created if this is the
    first time anyone has used it, and bound so the write that follows
    lands in it."""
    user = tenants_svc.resolve_personal(db, email)
    tenancy.bind(user.tenant_id, user.tenant.brand_slug)
    return user


def _mint_login_token(db: Session, user: User) -> str:
    """A sign-in link for the account the entity landed in. Imported
    from the auth router rather than reimplemented, so the token shape
    and TTL stay in one place."""
    from .auth import _mint_login_token as mint

    return mint(db, user)


def _send_started_email(user: User, kind: str, name: str, public_url: str, raw_token: str, locale: str) -> None:
    send_email(
        to=user.email,
        template_name="started.html",
        context={
            # The account is the address itself. That line is how the
            # owner of an address learns something landed in their
            # account when somebody else typed it.
            "account": user.email,
            "kind": kind,
            "name": name,
            "public_url": public_url,
            "login_url": build_url("auth/redeem", token=raw_token),
        },
        # The language the visitor filled the form in, which is the one
        # they were reading the app in.
        locale=locale,
    )


def _finish(db: Session, user: User, kind: str, slug: str, name: str, locale: str) -> StartedOut:
    public_url = f"{_PUBLIC_BASE}/{_PREFIXES[kind]}/{slug}"
    raw = _mint_login_token(db, user)
    _send_started_email(user, kind, name, public_url, raw, locale)
    logger.info("started_from_root", kind=kind)
    return StartedOut(public_url=public_url, slug=slug)


@router.post("/event", response_model=StartedOut, status_code=201)
@limiter.limit(Limits.PUBLIC_WRITE)
def start_event(request: Request, data: StartEvent, db: Session = Depends(get_db)) -> StartedOut:
    user = _resolve_account(db, data.email)
    access.assert_user_can_assign_chapter(db, user, data.event.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "event")
    event = entities.create_event(db, data.event, user)
    db.commit()
    # The event's public page is per occurrence, so the link names the
    # session the visitor will land on, not the event.
    slug = event_stats.link_slug(db, event.id)
    return _finish(db, user, "event", slug, event.name_nl or event.name_en or "", event.locale)


@router.post("/form", response_model=StartedOut, status_code=201)
@limiter.limit(Limits.PUBLIC_WRITE)
def start_form(request: Request, data: StartForm, db: Session = Depends(get_db)) -> StartedOut:
    user = _resolve_account(db, data.email)
    access.assert_user_can_assign_chapter(db, user, data.form.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "form")
    form = entities.create_form(db, data.form, user)
    db.commit()
    return _finish(db, user, "form", form.slug, form.name_nl or form.name_en or "", form.locale)


@router.post("/quiz", response_model=StartedOut, status_code=201)
@limiter.limit(Limits.PUBLIC_WRITE)
def start_quiz(request: Request, data: StartQuiz, db: Session = Depends(get_db)) -> StartedOut:
    user = _resolve_account(db, data.email)
    access.assert_user_can_assign_chapter(db, user, data.quiz.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "quiz")
    quiz = entities.create_form(db, data.quiz, user, mode="quiz")
    db.commit()
    return _finish(db, user, "quiz", quiz.slug, quiz.name_nl or quiz.name_en or "", quiz.locale)


@router.post("/compass", response_model=StartedOut, status_code=201)
@limiter.limit(Limits.PUBLIC_WRITE)
def start_compass(request: Request, data: StartCompass, db: Session = Depends(get_db)) -> StartedOut:
    user = _resolve_account(db, data.email)
    access.assert_user_can_assign_chapter(db, user, data.compass.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "compass")
    kompas = entities.create_form(db, data.compass, user, mode="compass")
    db.commit()
    return _finish(db, user, "compass", kompas.slug, kompas.name_nl or kompas.name_en or "", kompas.locale)


@router.post("/datepoll", response_model=StartedOut, status_code=201)
@limiter.limit(Limits.PUBLIC_WRITE)
def start_datepoll(request: Request, data: StartDatepoll, db: Session = Depends(get_db)) -> StartedOut:
    user = _resolve_account(db, data.email)
    access.assert_user_can_assign_chapter(db, user, data.datepoll.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "datepoll")
    poll = entities.create_datepoll(db, data.datepoll, user)
    db.commit()
    return _finish(db, user, "datepoll", poll.slug, poll.name_nl or poll.name_en or "", poll.locale)


@router.post("/chore", response_model=StartedOut, status_code=201)
@limiter.limit(Limits.PUBLIC_WRITE)
def start_roster(request: Request, data: StartRoster, db: Session = Depends(get_db)) -> StartedOut:
    user = _resolve_account(db, data.email)
    access.assert_user_can_assign_chapter(db, user, data.roster.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "roster")
    roster = entities.create_roster(db, data.roster, user)
    db.commit()
    return _finish(db, user, "roster", roster.slug, roster.name_nl or roster.name_en or "", roster.locale)
