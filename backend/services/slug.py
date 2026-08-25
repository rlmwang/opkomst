import re
import unicodedata

from nanoid import generate

# URL-safe alphabet, no easily-confused characters (no 0/O, 1/l/I).
_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"

# The app's own first-level routes under ``/{tenant}/``. A chapter's
# agenda lives at ``/{tenant}/{chapter}``, so a chapter slug that
# matched one of these would shadow a page of the organiser app. The
# collision suffixer treats them as taken, and
# ``tests/test_chapter_agenda.py`` walks the router table so a route
# added later can't quietly shadow a chapter that already exists.
RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "admin",
        "auth",
        "chapters",
        "chores",
        "datepolls",
        "events",
        "forms",
        "login",
        "logout",
        "register",
        "users",
    }
)


def new_slug(length: int = 8) -> str:
    """Generate a short, public, URL-friendly event slug."""
    return generate(_ALPHABET, length)


def chapter_slug(name: str) -> str:
    """A human-readable kebab slug for a chapter's public agenda URL
    (``/{tenant}/{chapter}``): lowercased, accents stripped, runs of
    non-alphanumerics collapsed to single hyphens, capped in length.

    Uniqueness (within the organisation) and the reserved-name rule are
    the caller's, via ``services.chapters._unique_slug``."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")[:50].strip("-")
    return slug or "afdeling"
