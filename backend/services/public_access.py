"""Public-surface resolvers for the by-slug and by-token routes.

Every public router does the same two lookups:

* **by slug** — resolve a live entity; unknown *and* archived both 410
  with the same message (the public surface never distinguishes "never
  existed" from "archived since you bookmarked it" — no info leak).
* **by token** — resolve a submission from its edit-token hash (404 if
  the token doesn't match), then guard on the parent entity's state
  (410 if the parent is gone/archived, or fails an entity-specific
  ``extra_guard`` such as the event's "already over" check).

Both resolvers bind the tenant of what they found (see
``services.tenancy``). A public URL carries no tenant, so this is where
one enters the picture: the entity behind the slug or the token decides
which organisation the rest of the request reads and writes in.

The per-entity variance is only the parent model, the FK to it, and the
410 message; the 404 "invalid link" copy is shared.
"""

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import edit_token, tenancy

# Shared across all by-token routes — a token that matches no submission.
_TOKEN_INVALID = "This edit link is not valid."


def resolve_by_slug(db: Session, model: Any, slug: str, *, gone_detail: str) -> Any:
    """Resolve a slug to a live (non-archived) entity. Unknown or
    archived both raise 410 with ``gone_detail``."""
    row = db.query(model).filter(model.slug == slug).first()
    if row is None or row.archived_at is not None:
        raise HTTPException(status_code=410, detail=gone_detail)
    tenancy.bind(row.tenant_id, row.tenant.brand_slug)
    return row


def resolve_by_token(
    db: Session,
    submission_model: Any,
    token: str,
    *,
    parent_model: Any,
    parent_fk: Any,
    gone_detail: str,
    extra_guard: Callable[[Any], bool] | None = None,
) -> Any:
    """Resolve an edit-link token to its submission and validate the
    parent. 404 if the token matches nothing; 410 (``gone_detail``) if
    the parent is missing/archived or ``extra_guard(parent)`` is true.

    ``parent_fk`` is the submission's FK column to the parent (e.g.
    ``Signup.event_id``); its value on the row locates the parent.
    """
    sub = (
        db.query(submission_model).filter(submission_model.edit_token_hash == edit_token.hash_edit_token(token)).first()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail=_TOKEN_INVALID)
    parent = db.query(parent_model).filter(parent_model.id == getattr(sub, parent_fk.key)).first()
    if parent is None or parent.archived_at is not None or (extra_guard is not None and extra_guard(parent)):
        raise HTTPException(status_code=410, detail=gone_detail)
    tenancy.bind(parent.tenant_id, parent.tenant.brand_slug)
    return sub
