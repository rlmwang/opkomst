"""Chapter-scoped form CRUD + organiser-side reads.

Six mutating endpoints (create / update / archive / restore /
delete) and four read endpoints (list active / list archived /
summary / submissions). All require an approved user; all are
scoped to the user's chapter via ``access.get_form_for_user``
(single) or ``access.list_filter`` (lists).

Public-by-slug surfaces (the public form fetch + submit) live
in ``routers/forms_public.py``.

The ``forms`` table holds both products, surveys and quizzes
(``docs/design-quizzes.md``), and they differ by an answer key, a score
and how the questions are walked through: nothing an organiser's CRUD
cares about. So this module is a factory and it is mounted twice, at
``/api/v1/forms`` and ``/api/v1/quizzes``. ``mode`` is what each mount
passes in, every read names it, and the log events and the ceiling kind
come from the same argument.

Copying this file for quizzes would have been ten endpoints of
identical chapter scoping, image handling and archive semantics kept in
step by hand.

Form CRUD mirrors the events router shape one-to-one: create,
list active, list archived, get, update, archive, restore,
delete-when-archived, summary, submissions CSV source.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..config import settings
from ..database import get_db
from ..models import Form, FormSubmission, User
from ..schemas.common import EditLinkRecoverOut
from ..schemas.forms import (
    FormCreate,
    FormListOut,
    FormOut,
    FormSubmissionOut,
    FormSummaryOut,
    FormUpdate,
    QuizSubmissionOut,
)
from ..services import access, crud, edit_token, entities, limits, quizzes
from ..services import forms as forms_svc
from ..services import image as image_svc
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()


def _named(name: str):
    """Rename an endpoint before the decorators above it see it.

    FastAPI and slowapi both key off ``__name__``, and a factory that
    builds the same routes twice hands them two functions with one
    name. slowapi then holds two limits against a single key and
    charges every request twice: found by ``test_submit_rate_limit_fires``
    firing on the 11th of 20 allowed submissions. Decorators apply
    bottom-up, so this one runs first and the two mounts register as
    ``submit_form`` and ``submit_quiz``."""

    def wrap(func):  # type: ignore[no-untyped-def]
        func.__name__ = name
        func.__qualname__ = name
        return func

    return wrap


def build_router(mode: str, *, prefix: str, tag: str, kind: str, noun: str) -> APIRouter:
    """One organiser CRUD surface for one of the two products.

    ``mode`` filters every read, ``kind`` is the ceiling bucket in
    ``services/limits``, and ``noun`` names the structured-log events
    (``form_updated`` / ``quiz_updated``) so a log line still says which
    product it was."""
    _MODE = mode
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.post("", response_model=FormOut, status_code=201)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"create_{noun}")
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
        limits.assert_can_add_entity(db, user.tenant, kind)
        form = entities.create_form(db, data, user, mode)
        db.commit()
        db.refresh(form)
        return forms_svc.to_out(db, form)

    @router.get("", response_model=list[FormListOut])
    def list_forms(
        chapter_id: str | None = None,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> list[FormListOut]:
        rows = (
            forms_svc.query(db, _MODE)
            .filter(access.list_filter(db, user, Form, chapter_id), Form.archived_at.is_(None))
            .order_by(Form.created_at.desc())
            .all()
        )
        return forms_svc.enrich(db, rows)

    @router.get("/archived", response_model=list[FormListOut])
    def list_archived_forms(
        chapter_id: str | None = None,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> list[FormListOut]:
        rows = (
            forms_svc.query(db, _MODE)
            .filter(access.list_filter(db, user, Form, chapter_id), Form.archived_at.is_not(None))
            .order_by(Form.archived_at.desc())
            .all()
        )
        return forms_svc.enrich(db, rows)

    @router.get("/{form_id}", response_model=FormOut)
    def get_form(
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        form = access.get_form_for_user(db, form_id, user, _MODE)
        return forms_svc.to_out(db, form)

    @router.put("/{form_id}", response_model=FormOut)
    @limiter.limit(Limits.ORG_WRITE)
    @_named(f"update_{noun}")
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
        form = access.get_form_for_user(db, form_id, user, _MODE)
        if data.chapter_id != form.chapter_id:
            access.assert_user_can_assign_chapter(db, user, data.chapter_id)

        form.name_nl = data.name_nl
        form.name_en = data.name_en
        form.description_nl = data.description_nl
        form.description_en = data.description_en
        form.image_artist_instagram = data.image_artist_instagram
        form.chapter_id = data.chapter_id
        form.locale = data.locale
        forms_svc.apply_questions(db, form.id, data.questions, _MODE)
        db.commit()
        db.refresh(form)
        logger.info(f"{noun}_updated", form_id=form.id, actor_id=user.id)
        return forms_svc.to_out(db, form)

    @router.post("/{form_id}/archive", response_model=FormOut)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"archive_{noun}")
    def archive_form(
        request: Request,
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        form = access.get_form_for_user(db, form_id, user, _MODE)
        crud.archive(db, form, log_event=f"{noun}_archived", actor_id=user.id)
        return forms_svc.to_out(db, form)

    @router.post("/{form_id}/restore", response_model=FormOut)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"restore_{noun}")
    def restore_form(
        request: Request,
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        form = access.get_form_for_user(db, form_id, user, _MODE)
        crud.restore(db, form, log_event=f"{noun}_restored", actor_id=user.id)
        return forms_svc.to_out(db, form)

    @router.delete("/{form_id}", status_code=204)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"delete_{noun}")
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
        form = access.get_form_for_user(db, form_id, user, _MODE)
        crud.hard_delete(
            db,
            form,
            log_event=f"{noun}_deleted",
            actor_id=user.id,
            conflict_detail=f"Archive the {noun} before deleting it",
        )

    @router.post("/{form_id}/image", response_model=FormOut)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"upload_image_{noun}")
    async def upload_form_image(
        request: Request,
        form_id: str,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        """Upload (or replace) the form's hero image — same 4:5 GitHub
        pipeline as events (``services/image.py``)."""
        if not settings.event_images_enabled:
            raise HTTPException(status_code=503, detail="Image storage is not configured")
        form = access.get_form_for_user(db, form_id, user, _MODE)
        raw = await file.read()
        timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
        try:
            form.image_path = image_svc.replace_entity_image(
                folder="forms",
                entity_id=form.id,
                raw=raw,
                timestamp_ms=timestamp_ms,
                previous=form.image_path,
            )
        except image_svc.ImageProcessingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except image_svc.GithubUploadError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        db.commit()
        db.refresh(form)
        logger.info(f"{noun}_image_uploaded", form_id=form.id, actor_id=user.id)
        return forms_svc.to_out(db, form)

    @router.delete("/{form_id}/image", response_model=FormOut)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"delete_image_{noun}")
    def delete_form_image(
        request: Request,
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        """Clear the reference and delete the file: nothing else points at
        it."""
        form = access.get_form_for_user(db, form_id, user, _MODE)
        if form.image_path is None:
            raise HTTPException(status_code=404, detail="No image to delete")
        dropped = form.image_path
        form.image_path = None
        db.commit()
        image_svc.delete(dropped)
        db.refresh(form)
        logger.info(f"{noun}_image_deleted", form_id=form.id, actor_id=user.id)
        return forms_svc.to_out(db, form)

    @router.get("/{form_id}/summary", response_model=FormSummaryOut)
    def form_summary(
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormSummaryOut:
        access.get_form_for_user(db, form_id, user, _MODE)
        average, best, out_of = quizzes.score_stats(db, form_id) if _MODE == "quiz" else (None, None, None)
        return FormSummaryOut(
            submission_count=forms_svc.submission_count(db, form_id),
            score_average=average,
            score_best=best,
            max_score=out_of,
            questions=forms_svc.question_aggregates(db, form_id),
        )

    @router.post("/{form_id}/submissions/{submission_id}/edit-link", response_model=EditLinkRecoverOut)
    @limiter.limit(Limits.ORG_WRITE)
    @_named(f"recover_edit_link_{noun}")
    def recover_submission_edit_link(
        request: Request,
        form_id: str,
        submission_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> EditLinkRecoverOut:
        """Organiser recovery of a respondent's lost magic link — rotates
        the token (never reveals it) and permanently stamps
        ``link_recovered_at``; see ``services/edit_token.recover``."""
        form = access.get_form_for_user(db, form_id, user, _MODE)
        sub = (
            db.query(FormSubmission)
            .filter(FormSubmission.id == submission_id, FormSubmission.form_id == form.id)
            .first()
        )
        if sub is None:
            raise HTTPException(status_code=404, detail="Submission not found")
        raw = edit_token.recover(sub)
        db.commit()
        logger.info(f"{noun}_edit_link_recovered", form_id=form.id, submission_id=submission_id, actor_id=user.id)
        return EditLinkRecoverOut(edit_token=raw)

    @router.get(
        "/{form_id}/submissions",
        # A taken quiz carries a score; a filled-in questionnaire does
        # not. One route, one shape per product.
        response_model=list[QuizSubmissionOut] if mode == "quiz" else list[FormSubmissionOut],
    )
    def form_submissions(
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> list[FormSubmissionOut] | list[QuizSubmissionOut]:
        """Per-submission rows, keyed by question id. CSV consumers
        map columns by question id; a separate lookup against the
        questions list gives them the prompt text.

        Privacy: ``submission_id`` is a random per-submission token
        with no link back to whoever submitted — same contract as
        the post-event feedback CSV."""
        access.get_form_for_user(db, form_id, user, _MODE)
        if _MODE == "quiz":
            return forms_svc.quiz_submissions(db, form_id)
        return forms_svc.submissions(db, form_id)

    return router


# The two mounts. Surveys keep the URL they had; quizzes get their own.
router = build_router("survey", prefix="/api/v1/forms", tag="forms", kind="form", noun="form")
quiz_router = build_router("quiz", prefix="/api/v1/quizzes", tag="quizzes", kind="quiz", noun="quiz")
