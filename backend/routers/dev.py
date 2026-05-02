"""Local-mode-only test fixtures.

The router is mounted in ``main.py`` iff ``settings.local_mode``
is True. Routes here short-circuit production flows that would
otherwise go through email round-trips — useful for Playwright
e2e tests that can't read structured logs.

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
from ..schemas.auth import AuthResponse, LoginLinkRequest

router = APIRouter(prefix="/api/v1/auth", tags=["dev"], include_in_schema=False)


@router.post("/dev-issue-token", response_model=AuthResponse)
def dev_issue_token(data: LoginLinkRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Mints a JWT for any registered email without going through
    the magic-link round-trip. Used by Playwright e2e tests."""
    user = _live_user_by_email(db, data.email)
    if user is None:
        raise HTTPException(status_code=404, detail="No such user")
    return AuthResponse(token=create_token(user.id), user=_user_out(db, user))
