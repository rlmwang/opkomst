"""Chapter-scoped form CRUD + organiser-side reads.

Six mutating endpoints (create / update / archive / restore /
delete) and four read endpoints (list active / list archived /
summary / submissions). All require an approved user; all are
scoped to the user's chapter via ``forms_svc.get_form_for_user``
(single) or ``_scope_filter`` (lists).

Public-by-slug surfaces (the public form fetch + submit) live
in ``routers/forms_public.py``.

Form CRUD mirrors the events router shape one-to-one: create,
list active, list archived, get, update, archive, restore,
delete-when-archived, summary, submissions CSV source.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from ..auth import require_approved
from ..database import get_db
from ..models import Form, FormResponse, User
from ..schemas.forms import (
    FormCreate,
    FormOut,
    FormSubmissionOut,
    FormSummaryOut,
    FormUpdate,
)
from ..services import access
from ..services import forms as forms_svc
from ..services.rate_limit import Limits, limiter
from ..services.slug import new_slug

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/forms", tags=["forms"])


def _list_filter(db: Session, user: User, chapter_id: str | None) -> ColumnElement[bool]:
    """WHERE clause for a form-list query. ``chapter_id`` is the
    optional UI filter; without it we return every form in the
    user's full chapter set. Mirrors ``events._list_filter``."""
    ids = access.chapter_ids_for_user(db, user)
    if not ids:
        from sqlalchemy import false

        return false()
    if chapter_id is None:
        return Form.chapter_id.in_(ids)
    access.assert_user_can_assign_chapter(db, user, chapter_id)
    return Form.chapter_id == chapter_id


@router.post("", response_model=FormOut, status_code=201)
@limiter.limit(Limits.ORG_RARE)
def create_form(
    request: Request,
    data: FormCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FormOut:
    """Create a new form. Questions are optional — a blank form
    can be saved and the question list filled in on the edit
    page afterwards. Caller-supplied ``chapter_id`` must be in
    the user's live membership set."""
    access.assert_user_can_assign_chapter(db, user, data.chapter_id)
    form = Form(
        slug=new_slug(),
        name=data.name,
        locale=data.locale,
        chapter_id=data.chapter_id,
        created_by=user.id,
    )
    db.add(form)
    db.flush()  # Need form.id for the question rows below.
    if data.questions:
        forms_svc.apply_questions(db, form.id, data.questions)
    db.commit()
    db.refresh(form)
    logger.info("form_created", form_id=form.id, actor_id=user.id, chapter_id=data.chapter_id)
    return FormOut.model_validate(forms_svc.to_out(db, form))


@router.get("", response_model=list[FormOut])
def list_forms(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[FormOut]:
    rows = (
        db.query(Form)
        .filter(_list_filter(db, user, chapter_id), Form.archived_at.is_(None))
        .order_by(Form.created_at.desc())
        .all()
    )
    return [FormOut.model_validate(forms_svc.to_out(db, r)) for r in rows]


@router.get("/archived", response_model=list[FormOut])
def list_archived_forms(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[FormOut]:
    rows = (
        db.query(Form)
        .filter(_list_filter(db, user, chapter_id), Form.archived_at.is_not(None))
        .order_by(Form.archived_at.desc())
        .all()
    )
    return [FormOut.model_validate(forms_svc.to_out(db, r)) for r in rows]


@router.get("/{form_id}", response_model=FormOut)
def get_form(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FormOut:
    form = forms_svc.get_form_for_user(db, form_id, user)
    return FormOut.model_validate(forms_svc.to_out(db, form))


@router.put("/{form_id}", response_model=FormOut)
@limiter.limit(Limits.ORG_WRITE)
def update_form(
    request: Request,
    form_id: str,
    data: FormUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FormOut:
    """Update a form. Chapter changes are allowed (organiser might
    have picked the wrong chapter at create time) but the new one
    still has to be in the user's set. Questions are diff-applied
    by id — see ``services/forms.apply_questions``."""
    form = forms_svc.get_form_for_user(db, form_id, user)
    if data.chapter_id != form.chapter_id:
        access.assert_user_can_assign_chapter(db, user, data.chapter_id)

    form.name = data.name
    form.chapter_id = data.chapter_id
    form.locale = data.locale
    forms_svc.apply_questions(db, form.id, data.questions)
    db.commit()
    db.refresh(form)
    logger.info("form_updated", form_id=form.id, actor_id=user.id)
    return FormOut.model_validate(forms_svc.to_out(db, form))


@router.post("/{form_id}/archive", response_model=FormOut)
@limiter.limit(Limits.ORG_RARE)
def archive_form(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FormOut:
    form = forms_svc.get_form_for_user(db, form_id, user)
    if form.archived_at is not None:
        raise HTTPException(status_code=409, detail="Already archived")
    form.archived_at = datetime.now(UTC)
    db.commit()
    db.refresh(form)
    logger.info("form_archived", form_id=form.id, actor_id=user.id)
    return FormOut.model_validate(forms_svc.to_out(db, form))


@router.post("/{form_id}/restore", response_model=FormOut)
@limiter.limit(Limits.ORG_RARE)
def restore_form(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FormOut:
    form = forms_svc.get_form_for_user(db, form_id, user)
    if form.archived_at is None:
        raise HTTPException(status_code=409, detail="Not archived")
    form.archived_at = None
    db.commit()
    db.refresh(form)
    logger.info("form_restored", form_id=form.id, actor_id=user.id)
    return FormOut.model_validate(forms_svc.to_out(db, form))


@router.delete("/{form_id}", status_code=204)
@limiter.limit(Limits.ORG_RARE)
def delete_form(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Hard-delete an archived form. Refuses if the form isn't
    archived first — accidentally hard-deleting a live form with
    responses would be a data-loss footgun. Cascades through
    ``form_questions`` / ``form_responses`` via the FK ON DELETE
    CASCADEs in the schema."""
    form = forms_svc.get_form_for_user(db, form_id, user)
    if form.archived_at is None:
        raise HTTPException(status_code=409, detail="Archive the form before deleting it")
    db.delete(form)
    db.commit()
    logger.info("form_deleted", form_id=form_id, actor_id=user.id)


@router.get("/{form_id}/summary", response_model=FormSummaryOut)
def form_summary(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FormSummaryOut:
    forms_svc.get_form_for_user(db, form_id, user)
    return FormSummaryOut(
        submission_count=forms_svc.submission_count(db, form_id),
        questions=forms_svc.question_aggregates(db, form_id),
    )


@router.get("/{form_id}/submissions", response_model=list[FormSubmissionOut])
def form_submissions(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[FormSubmissionOut]:
    """Per-submission rows, keyed by question id. CSV consumers
    map columns by question id; a separate lookup against the
    questions list gives them the prompt text.

    Privacy: ``submission_id`` is a random per-submission token
    with no link back to whoever submitted — same contract as
    the post-event feedback CSV."""
    form = forms_svc.get_form_for_user(db, form_id, user)
    questions_by_id = {q["id"]: q for q in forms_svc.to_out(db, form)["questions"]}  # type: ignore[index]

    rows = (
        db.query(FormResponse)
        .filter(FormResponse.form_id == form_id)
        .order_by(FormResponse.submission_id, FormResponse.created_at)
        .all()
    )

    grouped: dict[str, dict[str, object]] = {}
    created_by_sid: dict[str, datetime] = {}
    for r in rows:
        q = questions_by_id.get(r.question_id)
        if q is None:
            continue
        bucket = grouped.setdefault(r.submission_id, {})
        # First row for this submission gives us the canonical
        # ``created_at`` — within a submission the timestamps are
        # in the same ms but the rows insert in question order.
        created_by_sid.setdefault(r.submission_id, r.created_at)
        kind = q["kind"]
        if kind == "rating" and r.answer_int is not None:
            bucket[r.question_id] = r.answer_int
        elif kind in ("text", "short_text") and r.answer_text is not None:
            bucket[r.question_id] = r.answer_text
        elif kind in ("single_choice", "multi_choice") and r.answer_choices is not None:
            bucket[r.question_id] = list(r.answer_choices)

    return [
        FormSubmissionOut(submission_id=sid, created_at=created_by_sid[sid], answers=ans)  # type: ignore[arg-type]
        for sid, ans in grouped.items()
    ]
