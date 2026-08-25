import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, EmailStr, Field, model_validator

from ..services.sanitize import VISIBLE_MAX_LENGTH, html_to_text, sanitize_richtext
from ..services.slug import RESERVED_SLUGS

# Two-letter ISO language tag. Names the primary language of an
# organiser-authored entity: the public page's default view + fallback
# anchor. Two values today (nl / en); widen the literal if we ever
# localise per region. Shared by every organiser-authored entity schema.
Locale = Literal["nl", "en"]


def pick_localized(nl: str | None, en: str | None, locale: str) -> str | None:
    """Resolve a bilingual field to one string for a given locale: the
    requested language if it has content, else the other language, else
    None. The single fallback rule shared by rendering and email."""
    chosen = en if locale == "en" else nl
    other = nl if locale == "en" else en
    return chosen or other


class BilingualTitleMixin(BaseModel):
    """The bilingual ``name_nl`` / ``name_en`` title shared by every
    organiser-authored ``*Create`` payload. Blank strings collapse to
    None, and the primary-language title (per the payload's own
    ``locale``) is required — the translation stays optional."""

    name_nl: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _require_primary_name(self) -> "BilingualTitleMixin":
        self.name_nl = (self.name_nl or "").strip() or None
        self.name_en = (self.name_en or "").strip() or None
        locale = getattr(self, "locale", "nl")
        chosen = self.name_en if locale == "en" else self.name_nl
        if not chosen:
            raise ValueError("A title in the primary language is required.")
        return self


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


# Optional short free-text an organiser writes (a per-chore label). One
# shared cap so callers can't drift. Stored as unbounded ``Text``; the
# limit lives only here at the schema boundary.
Description = Annotated[str | None, Field(default=None, max_length=2000)]


def _sanitize_and_bound(value: str | None) -> str | None:
    """Sanitize an organiser-authored rich-text body to the allowlist,
    then reject anything whose *visible* text exceeds the cap. Sanitizing
    first means markup can't inflate the raw string past a length check,
    and a paste over the limit fails loudly with a field-named 422."""
    cleaned = sanitize_richtext(value)
    if cleaned is not None and len(html_to_text(cleaned)) > VISIBLE_MAX_LENGTH:
        raise ValueError(f"Text may be at most {VISIBLE_MAX_LENGTH} characters.")
    return cleaned


# The formatted "details" body shared by the four organiser-authored
# entities: the event ``topic`` and the form / datepoll / roster
# ``description``. Every write is sanitized server-side to a closed set
# of inline marks + safe links (``services/sanitize.py``); the stored
# HTML is therefore safe to render with ``v-html`` downstream. The
# ``max_length`` here bounds the *raw* HTML (markup inflates); the
# visible-text cap is enforced inside the validator.
RichText = Annotated[
    str | None,
    Field(default=None, max_length=8000),
    AfterValidator(_sanitize_and_bound),
]


def _validate_chapter_slug(v: str) -> str:
    """A chapter's public-agenda slug: lowercase kebab, and never one of
    the organiser app's own page names. The agenda lives at
    ``/{tenant}/{slug}``, so a chapter called ``events`` would shadow
    the events page."""
    v = v.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", v):
        raise ValueError("Slug may contain only lowercase letters, digits, and single hyphens.")
    if v in RESERVED_SLUGS:
        raise ValueError(f"Slug {v!r} is the name of a page in the app; pick another.")
    return v


# Human-readable chapter slug at the schema boundary. Shared by chapter
# create/patch so the two can't drift on what a valid slug is.
ChapterSlug = Annotated[str, Field(min_length=1, max_length=50), AfterValidator(_validate_chapter_slug)]


class EditLinkRecoverOut(BaseModel):
    """The freshly-minted raw edit token after an organiser recovers a
    participant's lost magic link (``services/edit_token.recover``).
    Handed out exactly once; the old link is invalidated and the row's
    ``link_recovered_at`` is stamped permanently. One shape for all
    four submission types."""

    edit_token: str
