"""Organisation-wide settings, read and written by its admins.

One resource: the tenant's own row, reduced to the fields it makes
sense to change from inside the app. The agenda window lives here
because it is a publishing decision (how far ahead this organisation
programmes) rather than a deployment one, and nobody should need a
CLI or a redeploy to make it.

Read is open to every approved member — the agenda window explains
what an organiser sees on the public page, so hiding it from them
would just produce questions. Writing is admin-only.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_approved, require_organisation
from ..database import get_db
from ..models import Tenant, User
from ..permissions import Action, can
from ..schemas.tenants import TenantSettingsOut, TenantSettingsUpdate
from ..services import tenancy
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

# Organisation-only surface: a personal tenant has no chapters, so no
# public agenda to bound and no admin to bound it.
router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(require_organisation)],
)


def _require(actor: User, action: Action) -> None:
    """403 unless the matrix says yes, exactly as ``routers/admin.py``
    does it. The role gate lives in ``permissions.can`` rather than in
    a ``require_admin`` dependency so the frontend's mirror of the
    matrix has an action to key its affordances on."""
    if not can(actor, action, tenant_kind=actor.tenant.kind):
        raise HTTPException(status_code=403, detail="Forbidden")


def _tenant(db: Session) -> Tenant:
    """The signed-in user's own tenant. Through the bound id rather
    than ``user.tenant`` so this reads on the request's session, like
    every other tenant-scoped lookup in the app."""
    tenant = db.get(Tenant, tenancy.current())
    if tenant is None:  # pragma: no cover - the FK makes this unreachable
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant


@router.get("", response_model=TenantSettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> TenantSettingsOut:
    _require(user, Action.READ_SETTINGS)
    return TenantSettingsOut.model_validate(_tenant(db))


@router.put("", response_model=TenantSettingsOut)
@limiter.limit(Limits.ORG_WRITE)
def update_settings(
    request: Request,
    data: TenantSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> TenantSettingsOut:
    _require(user, Action.UPDATE_SETTINGS)
    tenant = _tenant(db)
    tenant.agenda_future_days = data.agenda_future_days
    tenant.agenda_past_days = data.agenda_past_days
    db.commit()
    db.refresh(tenant)
    logger.info("settings_updated", outcome="ok", actor_id=user.id)
    return TenantSettingsOut.model_validate(tenant)
