"""Account management endpoints.

Every approved user can read this surface (list users, /me).
Mutations split into two tiers:

* **Admin-only**: approve, promote, demote, delete; chapter
  CRUD lives in ``routers/chapters.py``.
* **Self-service** (admin OR target == actor): rename, set
  chapters. A user can change their own display name and
  chapter memberships freely; promoting / demoting / deleting
  yourself is *not* among them — those would let one click
  give you admin or strip the org of its only admin.

The authorization decision is *not* made inline. Every handler
calls ``permissions.can(actor, action, target)`` and 403s on
``False``. The matrix lives in one pure function with
exhaustive unit tests; this module is intentionally just the
HTTP/DB scaffolding around it.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import User
from ..permissions import Action, can
from ..routers.auth import _user_out
from ..schemas.admin import (
    ApproveUserRequest,
    PendingCountOut,
    RenameUserRequest,
    SetUserChaptersRequest,
)
from ..schemas.auth import UserOut
from ..services import chapters as chapters_svc
from ..services import user_chapters as user_chapters_svc
from ..services.mail import build_url, send_email
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _get_live_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _require(actor: User, action: Action, target: User | None = None) -> None:
    """403 unless ``permissions.can`` says yes. The matrix is the
    single source of truth; this is the one-line bridge between
    the pure decision and the HTTP error contract."""
    if not can(actor, action, target):
        raise HTTPException(status_code=403, detail="Forbidden")


def _apply_user_change(
    db: Session,
    actor: User,
    target: User,
    *,
    mutate: Callable[[User], None],
    log_event: str,
    log_extras: dict[str, object] | None = None,
) -> UserOut:
    """Run ``mutate`` (which carries handler-specific preconditions
    and the actual write), commit, log, and return the canonical
    ``UserOut``. Authorization happens at the call site via
    ``_require`` before the target is even fetched in some
    handlers — keep that invariant."""
    mutate(target)
    db.commit()
    db.refresh(target)
    logger.info(log_event, actor_id=actor.id, target_id=target.id, **(log_extras or {}))
    return _user_out(db, target)


@router.get("/users/pending-count", response_model=PendingCountOut)
def pending_user_count(
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> PendingCountOut:
    """How many live users are awaiting admin approval. Backs the
    red-dot indicator on the navbar's Accounts link — only
    rendered for admins, and the endpoint is admin-only too so
    organisers can't sniff the count.

    Defined *before* ``GET /users`` so the static path beats
    FastAPI's parametric ``/users/{user_id}/...`` patterns; the
    explicit string segment wouldn't actually conflict with the
    list endpoint, but keeping all the static-segment routes up
    top is the cheapest way to never trip over that ordering rule
    in the future."""
    # ``Action.LIST_USERS`` is open to any approved actor; the
    # pending-count is a stricter view of the same data and we
    # want it admin-only. There's no Action for it because it's a
    # subset of the LIST decision — keep the matrix focused on
    # write operations and decide read sub-projections at the
    # endpoint level.
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    n = db.query(User).filter(User.deleted_at.is_(None), User.is_approved.is_(False)).count()
    return PendingCountOut(count=n)


@router.get("/users", response_model=list[UserOut])
def list_users(
    pending: bool = False,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> list[UserOut]:
    """Open to every approved user. Returns the same projection
    everyone else sees — names + email + chapter memberships.
    No "see only your own row" mode; the visibility matches the
    organising context the project is built for."""
    _require(actor, Action.LIST_USERS)
    q = db.query(User).filter(User.deleted_at.is_(None))
    if pending:
        q = q.filter(User.is_approved.is_(False))
    rows = q.order_by(User.created_at.desc()).all()
    return [_user_out(db, u) for u in rows]


def _resolve_live_chapters(db: Session, chapter_ids: list[str]) -> list:
    """Validate every id resolves to a live chapter; collect the
    Chapter rows in input order. 400 on any miss — the admin
    UI's MultiSelect already excludes archived chapters, so a
    miss here is a genuine bad-request, not a stale-cache race."""
    chapters = []
    for cid in chapter_ids:
        row = chapters_svc.find_by_id(db, cid)
        if row is None:
            raise HTTPException(
                status_code=400,
                detail="One or more chapters do not exist or are archived",
            )
        chapters.append(row)
    return chapters


@router.post("/users/{user_id}/approve", response_model=UserOut)
@limiter.limit(Limits.ORG_WRITE)
def approve_user(
    request: Request,
    user_id: str,
    data: ApproveUserRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> UserOut:
    """Mark a pending user approved and replace their membership
    set with ``chapter_ids``. The approval email lists every
    assigned chapter so the user knows the full scope of what
    they've been let into."""
    target = _get_live_user_or_404(db, user_id)
    _require(actor, Action.APPROVE_USER, target)
    chapters = _resolve_live_chapters(db, data.chapter_ids)

    def mutate(target: User) -> None:
        if target.is_approved:
            raise HTTPException(status_code=409, detail="Already approved")
        target.is_approved = True
        user_chapters_svc.set_chapters(db, target, data.chapter_ids)

    out = _apply_user_change(
        db,
        actor,
        target,
        mutate=mutate,
        log_event="user_approved",
        log_extras={"chapter_ids": data.chapter_ids},
    )
    # Notify the user — they registered and were waiting for this
    # gate to clear. The dashboard can act immediately on the link.
    send_email(
        to=out.email,
        template_name="approved.html",
        context={
            "name": out.name,
            "chapter_names": [c.name for c in chapters],
            "dashboard_url": build_url("dashboard"),
        },
        locale="nl",
    )
    return out


@router.post("/users/{user_id}/set-chapters", response_model=UserOut)
@limiter.limit(Limits.ORG_WRITE)
def set_user_chapters(
    request: Request,
    user_id: str,
    data: SetUserChaptersRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> UserOut:
    """Replace the user's full chapter membership set. Self-service:
    a user can manage their own chapter memberships without
    admin intervention. ``min_length=1`` on the schema keeps
    every approved user in at least one chapter — emptying the
    set would orphan you from the project."""
    target = _get_live_user_or_404(db, user_id)
    _require(actor, Action.SET_USER_CHAPTERS, target)
    _resolve_live_chapters(db, data.chapter_ids)

    added: set[str] = set()
    removed: set[str] = set()

    def mutate(target: User) -> None:
        nonlocal added, removed
        added, removed = user_chapters_svc.set_chapters(db, target, data.chapter_ids)

    return _apply_user_change(
        db,
        actor,
        target,
        mutate=mutate,
        log_event="user_chapters_set",
        # Diff in the audit line — log the *change*, not the full
        # final state, so the question "what did this actor do
        # at 14:32?" answers without diff'ing two snapshots.
        log_extras={
            "added": sorted(added),
            "removed": sorted(removed),
            "self_service": actor.id == target.id,
        },
    )


@router.post("/users/{user_id}/rename", response_model=UserOut)
@limiter.limit(Limits.ORG_WRITE)
def rename_user(
    request: Request,
    user_id: str,
    data: RenameUserRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> UserOut:
    """Update a user's display name. Self-service. The user-
    supplied value is stripped of surrounding whitespace; an
    empty-after-strip name is rejected before the row is touched
    (Pydantic's ``min_length`` doesn't strip)."""
    target = _get_live_user_or_404(db, user_id)
    _require(actor, Action.RENAME_USER, target)
    new_name = data.name.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="Name is required")

    def mutate(target: User) -> None:
        target.name = new_name

    return _apply_user_change(
        db,
        actor,
        target,
        mutate=mutate,
        log_event="user_renamed",
        log_extras={"new_name_len": len(new_name), "self_service": actor.id == target.id},
    )


@router.post("/users/{user_id}/promote", response_model=UserOut)
@limiter.limit(Limits.ORG_WRITE)
def promote_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> UserOut:
    target = _get_live_user_or_404(db, user_id)
    _require(actor, Action.PROMOTE_USER, target)

    def mutate(target: User) -> None:
        if target.role == "admin":
            raise HTTPException(status_code=409, detail="Already admin")
        if not target.is_approved:
            raise HTTPException(status_code=409, detail="Approve the user before promoting")
        target.role = "admin"

    return _apply_user_change(db, actor, target, mutate=mutate, log_event="user_promoted")


@router.post("/users/{user_id}/demote", response_model=UserOut)
@limiter.limit(Limits.ORG_WRITE)
def demote_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> UserOut:
    """Demote an admin back to organiser. The matrix blocks
    self-demotion — the same anti-foot-shoot rule that previously
    lived inline in this handler."""
    target = _get_live_user_or_404(db, user_id)
    _require(actor, Action.DEMOTE_USER, target)

    def mutate(target: User) -> None:
        if target.role != "admin":
            raise HTTPException(status_code=409, detail="Not an admin")
        target.role = "organiser"

    return _apply_user_change(db, actor, target, mutate=mutate, log_event="user_demoted")


@router.delete("/users/{user_id}", status_code=204)
@limiter.limit(Limits.ORG_RARE)
def delete_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approved),
) -> None:
    """Soft-delete a user. Stamps ``deleted_at``; the email slot
    frees up via the partial-unique index, so registering again
    with the same address restores the row in an unapproved
    state.

    Self-deletion is implicitly blocked because the permission
    matrix's DELETE_USER branch is admin-only and contains no
    self-service carve-out — an admin trying to delete their
    own row therefore goes through the matrix and is rejected
    by the explicit "not self" check we still keep here as
    defence in depth (and to give a clearer 409 over the
    matrix's blanket 403)."""
    target = _get_live_user_or_404(db, user_id)
    _require(actor, Action.DELETE_USER, target)
    if user_id == actor.id:
        raise HTTPException(status_code=409, detail="You cannot delete yourself")
    # Mark the row unapproved so the restore-via-register path can
    # be unconditional ("new account, fresh approval gate").
    target.is_approved = False
    target.deleted_at = datetime.now(UTC)
    db.commit()
    logger.info("user_deleted", actor_id=actor.id, target_id=target.id)
