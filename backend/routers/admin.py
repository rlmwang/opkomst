import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import AuditLog, User
from ..schemas.admin import AdminUserOut

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


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
    return [AdminUserOut.model_validate(u) for u in rows]


@router.post("/users/{user_id}/approve", response_model=AdminUserOut)
def approve_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_approved:
        raise HTTPException(status_code=409, detail="Already approved")
    target.is_approved = True
    db.add(AuditLog(actor_id=admin.id, action="approve", target_id=target.id))
    db.commit()
    db.refresh(target)
    logger.info("user_approved", actor_id=admin.id, target_id=target.id)
    return AdminUserOut.model_validate(target)


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
    return AdminUserOut.model_validate(target)


@router.post("/users/{user_id}/demote", response_model=AdminUserOut)
def demote_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    """Demote an admin back to organiser. Self-demotion is blocked so the
    venue can never end up with zero admins via a single click."""
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
    return AdminUserOut.model_validate(target)
