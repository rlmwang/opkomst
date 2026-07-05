"""Respondent edit-link tokens.

A public submission (event sign-up, form, datepoll) mints one secret
token at creation. The raw token is handed to the submitter once (in
the submit response, surfaced as a magic edit link) and then only its
SHA-256 hash is kept, on the submission row's ``edit_token_hash``
column. A DB dump therefore can't reconstruct a working edit link, and
the organiser never sees the token — it grants edit access to exactly
that one submission, to whoever holds the link.

Lookup is by hash: ``WHERE edit_token_hash = hash_edit_token(raw)``.
The token is reusable (edit repeatedly) and lives as long as the
submission row; it 410s once the parent entity is no longer public.

**Recovery** (``recover``): when a participant loses their link, an
organiser can re-mint it. Because only the hash is stored, recovery
can never *reveal* the existing link — it rotates the token (the old
link stops working) and permanently stamps ``link_recovered_at``, so
the public edit page always discloses that an organiser has held the
link. One shared mechanism for all four submission rows (Signup,
FormSubmission, DatepollSubmission, Volunteer) via ``EditTokenMixin``.
"""

import hashlib
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import DatepollSubmission, FormSubmission, Signup, Volunteer


def new_edit_token() -> tuple[str, str]:
    """Return ``(raw, hash)``. Store the hash on the submission; hand
    the raw to the client exactly once."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_edit_token(raw)


def hash_edit_token(raw: str) -> str:
    """SHA-256 hex of the raw token — what's persisted and what we
    look up by."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def recover(row: "Signup | FormSubmission | DatepollSubmission | Volunteer") -> str:
    """Organiser recovery: rotate the row's secret link and return the
    new raw token (to hand to the organiser exactly once). Invalidates
    the old link and stamps ``link_recovered_at`` — stamped on *every*
    recovery (the banner shows the most recent copy), never cleared.
    Does not commit; the calling route does."""
    raw, token_hash = new_edit_token()
    row.edit_token_hash = token_hash
    row.link_recovered_at = datetime.now(UTC)
    return raw
