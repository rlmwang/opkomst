from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field


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
