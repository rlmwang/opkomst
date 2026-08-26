"""Local-mode-only test fixtures and dev-server helpers.

The router is mounted in ``main.py`` iff ``settings.local_mode``
is True. Routes here short-circuit production flows that would
otherwise go through email round-trips (useful for Playwright
e2e tests that can't read structured logs), or answer a question
the Vite dev server can only answer with a database.

Never reachable in production: the router itself isn't mounted
when ``LOCAL_MODE`` is unset, so any request hits FastAPI's
default 404 handler. The previous implementation lived in
``routers/auth.py`` with a ``settings.local_mode`` early-return
guard; this file makes the gating explicit at mount time so
the auth router stops carrying test-only routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import create_token
from ..database import get_db
from ..routers.auth import _live_user_by_email, _user_out
from ..routers.spa import brand_slug_for
from ..schemas.auth import AuthResponse, LoginLinkRequest
from ..services import tenancy
from ..services import tenants as tenants_svc

router = APIRouter(prefix="/api/v1", tags=["dev"], include_in_schema=False)


@router.get("/dev-public-brand/{prefix}/{slug}")
def dev_public_brand(prefix: str, slug: str, db: Session = Depends(get_db)) -> dict[str, str]:
    """The brand folder ``/{prefix}/{slug}`` wears. In production the
    same answer is baked into the served HTML by ``routers/spa.py``; the
    dev server serves the shells itself and has no database, so it asks
    here rather than guessing an organisation."""
    return {"slug": brand_slug_for(db, prefix, slug)}


@router.post("/auth/dev-issue-token", response_model=AuthResponse)
def dev_issue_token(data: LoginLinkRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Mints a JWT for any registered email without going through the
    magic-link round-trip. Used by Playwright e2e tests. Same two doors
    as the real flow: with a tenant slug the address is looked up inside
    that organisation, without one it is the personal account."""
    if data.tenant is None:
        user = tenants_svc.find_personal_user_by_email(db, data.email)
    else:
        tenant = tenants_svc.find_live_organisation_by_slug(db, data.tenant)
        if tenant is None:
            raise HTTPException(status_code=404, detail="No such tenant")
        user = _live_user_by_email(db, data.email, tenant.id)
    if user is None:
        raise HTTPException(status_code=404, detail="No such user")
    tenancy.bind(user.tenant_id, user.tenant.brand_slug)
    return AuthResponse(token=create_token(user), user=_user_out(db, user))
