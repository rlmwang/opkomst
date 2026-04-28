import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import AuditLog, User
from ..schemas.admin import AdminUserOut, ApproveUserRequest, AssignChapterRequest
from ..services import chapters as chapters_svc
from ..services import scd2
from ..services.email.sender import send_email
from ..services.email.urls import build_url

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _admin_user_out(db: Session, user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.entity_id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=user.is_approved,
        chapter_id=user.chapter_id,
        chapter_name=chapters_svc.name_for_entity(db, user.chapter_id),
        created_at=user.created_at,
    )


def _get_user_or_404(db: Session, entity_id: str) -> User:
    user = scd2.current_by_entity(db, User, entity_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    pending: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[AdminUserOut]:
    q = scd2.current(db.query(User))
    if pending:
        q = q.filter(User.is_approved.is_(False))
    rows = q.order_by(User.created_at.desc()).all()
    return [_admin_user_out(db, u) for u in rows]


@router.post("/users/{entity_id}/approve", response_model=AdminUserOut)
def approve_user(
    entity_id: str,
    data: ApproveUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    target = _get_user_or_404(db, entity_id)
    if target.is_approved:
        raise HTTPException(status_code=409, detail="Already approved")
    chapter = chapters_svc.find_current_by_entity(db, data.chapter_id)
    if chapter is None:
        raise HTTPException(status_code=400, detail="Chapter does not exist or is archived")
    new_target = scd2.scd2_update(
        db,
        target,
        changed_by=admin.entity_id,
        is_approved=True,
        chapter_id=data.chapter_id,
    )
    db.add(AuditLog(actor_id=admin.entity_id, action="approve", target_id=target.entity_id))
    db.commit()
    db.refresh(new_target)
    logger.info(
        "user_approved",
        actor_id=admin.entity_id,
        target_id=new_target.entity_id,
        chapter_id=data.chapter_id,
    )
    # Notify the user — they registered, verified their email, and
    # were waiting for this gate to clear. The dashboard can act
    # immediately on the link.
    send_email(
        to=new_target.email,
        template_name="approved.html",
        context={
            "name": new_target.name,
            "chapter_name": chapter.name,
            "dashboard_url": build_url("dashboard"),
        },
        locale="nl",
    )
    return _admin_user_out(db, new_target)


@router.post("/users/{entity_id}/assign-chapter", response_model=AdminUserOut)
def assign_chapter(
    entity_id: str,
    data: AssignChapterRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    """Move a user to a different chapter. Approved users always have
    one; setting NULL is not supported through this endpoint."""
    target = _get_user_or_404(db, entity_id)
    chapter = chapters_svc.find_current_by_entity(db, data.chapter_id)
    if chapter is None:
        raise HTTPException(status_code=400, detail="Chapter does not exist or is archived")
    new_target = scd2.scd2_update(
        db,
        target,
        changed_by=admin.entity_id,
        chapter_id=data.chapter_id,
    )
    db.add(AuditLog(actor_id=admin.entity_id, action="assign_chapter", target_id=target.entity_id))
    db.commit()
    db.refresh(new_target)
    logger.info(
        "user_chapter_assigned",
        actor_id=admin.entity_id,
        target_id=new_target.entity_id,
        chapter_id=data.chapter_id,
    )
    return _admin_user_out(db, new_target)


@router.post("/users/{entity_id}/promote", response_model=AdminUserOut)
def promote_user(
    entity_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    target = _get_user_or_404(db, entity_id)
    if target.role == "admin":
        raise HTTPException(status_code=409, detail="Already admin")
    if not target.is_approved:
        raise HTTPException(status_code=409, detail="Approve the user before promoting")
    new_target = scd2.scd2_update(
        db,
        target,
        changed_by=admin.entity_id,
        role="admin",
    )
    db.add(AuditLog(actor_id=admin.entity_id, action="promote", target_id=target.entity_id))
    db.commit()
    db.refresh(new_target)
    logger.info("user_promoted", actor_id=admin.entity_id, target_id=new_target.entity_id)
    return _admin_user_out(db, new_target)


@router.delete("/users/{entity_id}", status_code=204)
def delete_user(
    entity_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    """Soft-delete a user. Closes the SCD2 chain (``valid_until`` set,
    no replacement). The user can no longer log in — their email frees
    up the partial-unique slot, so registering again with the same
    address restores the chain in an unapproved state.

    Self-deletion is blocked so the org can't lock itself out via a
    single click."""
    if entity_id == admin.entity_id:
        raise HTTPException(status_code=409, detail="You cannot delete yourself")
    target = _get_user_or_404(db, entity_id)
    # Mark the closed row unapproved so the restore-via-register path
    # can be unconditional ("new account, fresh approval gate").
    target.is_approved = False
    scd2.scd2_close(db, target, changed_by=admin.entity_id, change_kind="archived")
    db.add(AuditLog(actor_id=admin.entity_id, action="delete", target_id=target.entity_id))
    db.commit()
    logger.info("user_deleted", actor_id=admin.entity_id, target_id=target.entity_id)


@router.post("/users/{entity_id}/demote", response_model=AdminUserOut)
def demote_user(
    entity_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    """Demote an admin back to organiser. Self-demotion is blocked so
    the org can never end up with zero admins via a single click."""
    if entity_id == admin.entity_id:
        raise HTTPException(status_code=409, detail="You cannot demote yourself")
    target = _get_user_or_404(db, entity_id)
    if target.role != "admin":
        raise HTTPException(status_code=409, detail="Not an admin")
    new_target = scd2.scd2_update(
        db,
        target,
        changed_by=admin.entity_id,
        role="organiser",
    )
    db.add(AuditLog(actor_id=admin.entity_id, action="demote", target_id=target.entity_id))
    db.commit()
    db.refresh(new_target)
    logger.info("user_demoted", actor_id=admin.entity_id, target_id=new_target.entity_id)
    return _admin_user_out(db, new_target)
