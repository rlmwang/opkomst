import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import AuditLog, User
from ..schemas.admin import AdminUserOut, ApproveUserRequest, AssignAfdelingRequest
from ..services import afdelingen as afdelingen_svc

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _admin_user_out(db: Session, user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=user.is_approved,
        afdeling_id=user.afdeling_id,
        afdeling_name=afdelingen_svc.name_for_entity(db, user.afdeling_id),
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    pending: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[AdminUserOut]:
    q = db.query(User)
    if pending:
        q = q.filter(User.is_approved.is_(False))
    rows = q.order_by(User.created_at.desc()).all()
    return [_admin_user_out(db, u) for u in rows]


@router.post("/users/{user_id}/approve", response_model=AdminUserOut)
def approve_user(
    user_id: str,
    data: ApproveUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_approved:
        raise HTTPException(status_code=409, detail="Already approved")
    afdeling = afdelingen_svc.find_current_by_entity(db, data.afdeling_id)
    if afdeling is None:
        raise HTTPException(status_code=400, detail="Afdeling does not exist or is archived")
    target.is_approved = True
    target.afdeling_id = data.afdeling_id
    db.add(AuditLog(actor_id=admin.id, action="approve", target_id=target.id))
    db.commit()
    db.refresh(target)
    logger.info(
        "user_approved",
        actor_id=admin.id,
        target_id=target.id,
        afdeling_id=data.afdeling_id,
    )
    return _admin_user_out(db, target)


@router.post("/users/{user_id}/assign-afdeling", response_model=AdminUserOut)
def assign_afdeling(
    user_id: str,
    data: AssignAfdelingRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    """Move a user to a different afdeling. Approved users always
    have one; setting NULL is not supported through this endpoint."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    afdeling = afdelingen_svc.find_current_by_entity(db, data.afdeling_id)
    if afdeling is None:
        raise HTTPException(status_code=400, detail="Afdeling does not exist or is archived")
    target.afdeling_id = data.afdeling_id
    db.add(AuditLog(actor_id=admin.id, action="assign_afdeling", target_id=target.id))
    db.commit()
    db.refresh(target)
    logger.info(
        "user_afdeling_assigned",
        actor_id=admin.id,
        target_id=target.id,
        afdeling_id=data.afdeling_id,
    )
    return _admin_user_out(db, target)


@router.post("/users/{user_id}/promote", response_model=AdminUserOut)
def promote_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "admin":
        raise HTTPException(status_code=409, detail="Already admin")
    if not target.is_approved:
        raise HTTPException(status_code=409, detail="Approve the user before promoting")
    target.role = "admin"
    db.add(AuditLog(actor_id=admin.id, action="promote", target_id=target.id))
    db.commit()
    db.refresh(target)
    logger.info("user_promoted", actor_id=admin.id, target_id=target.id)
    return _admin_user_out(db, target)


@router.post("/users/{user_id}/demote", response_model=AdminUserOut)
def demote_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    """Demote an admin back to organiser. Self-demotion is blocked so
    the org can never end up with zero admins via a single click."""
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot demote yourself")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role != "admin":
        raise HTTPException(status_code=409, detail="Not an admin")
    target.role = "organiser"
    db.add(AuditLog(actor_id=admin.id, action="demote", target_id=target.id))
    db.commit()
    db.refresh(target)
    logger.info("user_demoted", actor_id=admin.id, target_id=target.id)
    return _admin_user_out(db, target)
