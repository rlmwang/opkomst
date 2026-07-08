import re
import unicodedata

from nanoid import generate

# URL-safe alphabet, no easily-confused characters (no 0/O, 1/l/I).
_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"

# A public event slug is exactly 8 chars from ``_ALPHABET``. This regex
# is the single source of truth for "does this ident have the event
# shape?", shared by the ``/e/{ident}`` dispatch in ``routers/spa.py``
# and the chapter-slug validator so the two can never disagree.
_EVENT_SLUG_RE = re.compile(rf"^[{_ALPHABET}]{{8}}$")


def new_slug(length: int = 8) -> str:
    """Generate a short, public, URL-friendly event slug."""
    return generate(_ALPHABET, length)


def is_event_slug(ident: str) -> bool:
    """True when ``ident`` has the exact shape of an event slug (8 chars
    from the nanoid alphabet). Used to route ``/e/{ident}`` to the event
    page vs the chapter agenda."""
    return bool(_EVENT_SLUG_RE.match(ident))


def chapter_slug(name: str) -> str:
    """A human-readable kebab slug for a chapter's public agenda URL
    (``/e/{chapter}``): lowercased, accents stripped, runs of
    non-alphanumerics collapsed to single hyphens, capped in length.

    Guaranteed **never** to match the event-slug shape (8 chars from the
    nanoid alphabet), so ``/e/{ident}`` dispatch stays unambiguous: a
    colliding result gets a ``-1`` suffix. Uniqueness across live chapters
    is enforced separately by the caller (partial-unique index)."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")[:50].strip("-")
    slug = slug or "afdeling"
    if _EVENT_SLUG_RE.match(slug):
        slug = f"{slug}-1"
    return slug
