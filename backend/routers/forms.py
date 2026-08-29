"""Chapter-scoped form CRUD + organiser-side reads.

Six mutating endpoints (create / update / archive / restore /
delete) and four read endpoints (list active / list archived /
summary / submissions). All require an approved user; all are
scoped to the user's chapter via ``access.get_form_for_user``
(single) or ``access.list_filter`` (lists).

Public-by-slug surfaces (the public form fetch + submit) live
in ``routers/forms_public.py``.

The ``forms`` table holds three products: surveys, quizzes
(``docs/design-quizzes.md``) and kompassen (``docs/design-kompas.md``).
They differ by what an answer means, what is derived from it and how
the questions are walked through: nothing an organiser's CRUD cares
about. So this module is a factory and it is mounted three times, at
``/api/v1/form``, ``/api/v1/quiz`` and ``/api/v1/compass``.
``mode`` is what each mount passes in, every read names it, and the log
events and the ceiling kind come from the same argument.

Copying this file per product would have been ten endpoints of
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
        rows = db.execute(
            access.scoped_select(db, Form, user, *forms_svc.LIST_COLUMNS, chapter_id=chapter_id)
            # The table holds three products, so the mode predicate is
            # part of every read of it (``forms_svc.query``).
            .where(Form.mode == _MODE, Form.archived_at.is_(None))
            .order_by(Form.created_at.desc())
        ).all()
        return forms_svc.enrich(db, rows)

    @router.get("/archived", response_model=list[FormListOut])
    def list_archived_forms(
        chapter_id: str | None = None,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> list[FormListOut]:
        return forms_svc.archived_enrich(db, access.archived_rows(db, "forms", user, chapter_id, mode=_MODE))

    @router.get("/{form_id}", response_model=FormOut)
    def get_form(
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        return forms_svc.to_out(
            db,
            access.get_scoped_row(
                db,
                Form,
                form_id,
                user,
                *forms_svc.FULL_COLUMNS,
                not_found="Form not found",
                where=Form.mode == _MODE,
            ),
        )

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
        form.reveal_answers = data.reveal_answers
        form.answers_editable = data.answers_editable
        form.name_required = data.name_required
        if _MODE == "compass":
            forms_svc.apply_axes(db, form.id, data.axes)
        forms_svc.apply_questions(db, form.id, data.questions, _MODE, data.axes)
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
        # Projected before the move: afterwards there is no live row.
        out = forms_svc.to_out(db, form)
        crud.archive_entity(db, form, root="forms", log_event=f"{noun}_archived", actor_id=user.id)
        return out.model_copy(update={"archived": True})

    @router.post("/{form_id}/restore", response_model=FormOut)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"restore_{noun}")
    def restore_form(
        request: Request,
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> FormOut:
        access.archived_row(db, "forms", form_id, user)
        crud.restore_entity(db, root="forms", entity_id=form_id, log_event=f"{noun}_restored", actor_id=user.id)
        return forms_svc.to_out(db, access.get_form_for_user(db, form_id, user, _MODE))

    @router.delete("/{form_id}", status_code=204)
    @limiter.limit(Limits.ORG_RARE)
    @_named(f"delete_{noun}")
    def delete_form(
        request: Request,
        form_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_approved),
    ) -> None:
        """Delete an archived form for good, with its questions,
        submissions and responses, and the image it owned. A live form is
        not found here at all, so deleting one still means archiving it
        first."""
        row = access.archived_row(db, "forms", form_id, user)
        crud.purge_entity(
            db,
            root="forms",
            entity_id=form_id,
            image_path=row["image_path"],
            log_event=f"{noun}_deleted",
            actor_id=user.id,
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
        form = access.get_form_for_user(db, form_id, user, _MODE)
        # Read once and handed to each half below. Every part of this
        # page is about the same questions, and each used to fetch its
        # own copy of them.
        questions = forms_svc.questions_of(db, form_id)
        average, best, out_of = quizzes.score_stats(db, form_id, questions) if _MODE == "quiz" else (None, None, None)
        return FormSummaryOut(
            submission_count=forms_svc.submission_count(db, form_id),
            score_average=average,
            score_best=best,
            max_score=out_of,
            compass=forms_svc.compass_summary(db, form, questions),
            questions=forms_svc.question_aggregates(db, form_id, questions),
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
        return forms_svc.submissions(db, form_id, mode=_MODE)

    return router


# The three mounts. Surveys keep the URL they had; the other two get
# their own.
router = build_router("survey", prefix="/api/v1/form", tag="forms", kind="form", noun="form")
quiz_router = build_router("quiz", prefix="/api/v1/quiz", tag="quizzes", kind="quiz", noun="quiz")
compass_router = build_router("compass", prefix="/api/v1/compass", tag="compasses", kind="compass", noun="compass")
