from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, EmailStr, Field


def _to_lower(v: str) -> str:
    return v.lower()


# Email type that lowercases at the schema boundary. Use everywhere the
# value identifies a User. Storage and downstream comparisons assume lowercase.
LowercaseEmail = Annotated[EmailStr, AfterValidator(_to_lower)]


def _clean_pseudonym(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


# Self-chosen pseudonym on a public submission — "a name, real or not".
# Optional, capped at 100, whitespace-only collapses to None (anonymous).
# One contract shared by the event sign-up and the datepoll respondent
# name so the two can't drift; the frontend renders NULL as a localised
# "Anonymous".
DisplayName = Annotated[str | None, Field(default=None, max_length=100), AfterValidator(_clean_pseudonym)]


def _clean_instagram_handle(v: str | None) -> str | None:
    """Strip whitespace, drop a leading ``@``, treat empty as null, and
    enforce Instagram's character set so a typo can't land in a public
    URL. Shared by the image-credit field on events / forms / datepolls."""
    if v is None:
        return None
    v = v.strip().lstrip("@")
    if not v:
        return None
    if not all(c.isalnum() or c in "._" for c in v):
        raise ValueError("Instagram handle may only contain letters, digits, '.', and '_'.")
    return v


# Optional Instagram handle crediting the image's designer. Shared by
# the hero-image block on all three organiser-authored entities.
InstagramHandle = Annotated[str | None, Field(default=None, max_length=30), BeforeValidator(_clean_instagram_handle)]
