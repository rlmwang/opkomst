from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import get_db
from .models import User
from .services import tenancy

_JWT_SECRET = settings.jwt_secret.get_secret_value()
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 24 * 7

ROLE_RANK: dict[str, int] = {"organiser": 1, "admin": 2}


def create_token(user: User) -> str:
    """Sign a JWT against the user's stable ``id``, carrying the tenant
    they belong to. Soft-delete invalidates the JWT
    (``get_current_user`` rejects via the ``deleted_at IS NULL``
    filter); rotation of ``JWT_SECRET`` is the only blanket
    revocation.

    The tenant claim is what makes cross-tenant access impossible by
    construction: the organiser API never reads a tenant off the URL,
    only off the token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "tenant": user.tenant_id,
        # The brand rides along so the tenant can be bound, data and
        # brand both, from the token alone, with no query, before the
        # request reaches a route. It is the brand folder rather than
        # the slug because that is the only thing the binding is read
        # for, and for a personal account the two differ.
        "tenant_brand": user.tenant.brand_slug,
        "iat": now,
        "exp": now + timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=JWT_ALGORITHM)


def _claims(token: str) -> tuple[str, str, str]:
    """``(user_id, tenant_id, tenant_brand)`` from a valid token."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    sub = payload.get("sub")
    tenant = payload.get("tenant")
    tenant_brand = payload.get("tenant_brand")
    if not isinstance(sub, str) or not isinstance(tenant, str) or not isinstance(tenant_brand, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return sub, tenant, tenant_brand


class TenantBindingMiddleware(BaseHTTPMiddleware):
    """Bind the signed-in user's tenant for the whole request.

    It has to happen here rather than in ``get_current_user``: a sync
    dependency runs in its own worker thread with its own copy of the
    context, so a bind made there is invisible to the endpoint that
    follows. Middleware runs in the request's async context, which every
    later thread hop inherits.

    The tenant comes from the JWT's own claims — no database, and no
    trust in anything the client can set independently of the signature.
    An absent or unreadable token binds nothing: public routes bind
    their own tenant from the entity the slug resolves to, and routes
    that need a user still 401 in ``get_current_user``."""

    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        header = request.headers.get("authorization")
        if header and header.lower().startswith("bearer "):
            try:
                _sub, tenant_id, tenant_brand = _claims(header.split(" ", 1)[1])
            except HTTPException:
                pass
            else:
                tenancy.bind(tenant_id, tenant_brand)
        return await call_next(request)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    user_id, tenant_id, _brand = _claims(token)
    user = (
        db.query(User)
        # The tenant comes back with the user rather than as a lazy load
        # a line later: every authenticated request reads ``brand_slug``
        # below, so this is one round trip on every request in the app,
        # not an optimisation for one endpoint.
        .options(joinedload(User.tenant))
        .filter(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    # Everything this request creates lands in the signed-in user's
    # tenant, without a single write site having to remember to say so.
    tenancy.bind(user.tenant_id, user.tenant.brand_slug)
    return user


def require_approved(user: User = Depends(get_current_user)) -> User:
    """An admin must have approved the account before an organiser can
    do anything beyond fetching /me. Email ownership is implicit —
    the user only got a JWT by clicking a magic link delivered to
    their address."""
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account is awaiting admin approval")
    return user


def require_organisation(user: User = Depends(get_current_user)) -> User:
    """Gate for the surfaces only an organisation has: users, chapters,
    the WhatsApp tool. A personal tenant is one person with no chapters
    and nobody to administer, so these routes don't exist for it.

    404 rather than 403: the surface doesn't advertise what other kinds
    of account have. Mounted as a router-level dependency so a new
    endpoint under those prefixes is covered without remembering."""
    if user.tenant.is_personal:
        raise HTTPException(status_code=404, detail="Not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account is awaiting admin approval")
    return user
