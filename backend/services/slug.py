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
def _content_pages() -> tuple:
    """Imported lazily: ``services.content`` is plain data, but keeping
    the import inside the call avoids a cycle if it ever grows one."""
    from .content import PAGES

    return PAGES


RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        # The organiser app's own pages. A chapter agenda lives at
        # ``/{tenant}/{chapter}`` and the personal app lives at the
        # root, so both namespaces share these names.
        "admin",
        "auth",
        "chapters",
        "chores",
        "compasses",
        "datepolls",
        "events",
        "forms",
        "quizzes",
        "logout",
        "register",
        "settings",
        "users",
        # The rest of the root's vocabulary: an organisation slug that
        # matched one of these would shadow a public page or a mount.
        "api",
        "assets",
        "brand",
        "c",
        "d",
        "e",
        "f",
        "k",
        "health",
        "me",
        "privacy",
        "voorwaarden",
        "robots.txt",
        "ads.txt",
        "sitemap.xml",
    }
    # The written pages are top-level paths too, so an organisation or
    # a chapter named after one would shadow it. One list, in
    # ``services/content.py``.
    | {page.slug for page in _content_pages()}
)


def new_slug(length: int = 8) -> str:
    """Generate a short, public, URL-friendly event slug."""
    return generate(_ALPHABET, length)


def personal_slug() -> str:
    """A personal tenant's slug. It names the row and never appears in a
    URL — the personal app lives at the root — so it is a nanoid rather
    than anything derived from the person: no organisation name someone
    might want later can collide with it, and it discloses nothing."""
    return new_slug()


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
