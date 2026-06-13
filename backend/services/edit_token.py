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
"""

import hashlib
import secrets


def new_edit_token() -> tuple[str, str]:
    """Return ``(raw, hash)``. Store the hash on the submission; hand
    the raw to the client exactly once."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_edit_token(raw)


def hash_edit_token(raw: str) -> str:
    """SHA-256 hex of the raw token — what's persisted and what we
    look up by."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
