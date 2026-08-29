"""The written pages: markdown files, and the one list built from them.

Ten pages of forms is a thin site, and no amount of metadata fixes that
(``docs/seo.md``). These are the pages that answer the question somebody
actually types, and each one ends by pointing at the thing in the app
that solves it.

Server-rendered rather than routes in the SPA, for the same reason
``/privacy`` is: a page written to be found should be readable in the
HTML that arrives, not after a bundle has loaded and rendered. The text
is on screen before anything else runs, including the ad tag these pages
carry (``docs/ads.md``); the policy page next door carries none.

**One file per page.** ``backend/content/{slug}.md`` holds the front
matter and the prose, and the filename is the URL. A page used to be a
Jinja template plus an entry in a tuple here, which is two places to
edit and one of them easy to forget. Adding a page is now adding a file.

The markdown is rendered once, at import, because it cannot change
between deploys. The router serves from this list, the sitemap is
generated from it, the footer mirrors it, and ``tests/test_content.py``
checks that mirror still agrees.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from functools import cached_property

import markdown

CONTENT_DIR = pathlib.Path(__file__).resolve().parent.parent / "content"

# ``tables`` for the two-column question tables, ``attr_list`` for the
# ``{: .note }`` a paragraph occasionally carries. Nothing else: this
# input is the repository, not anything a user typed, and every
# extension is one more shape to keep an eye on.
_MARKDOWN = markdown.Markdown(extensions=["tables", "attr_list"])

# Front-matter keys every page must carry. Missing one is a broken page
# rather than a page with a default, so the loader says so at import.
_REQUIRED = ("title", "description", "cta_path", "cta_label", "order")


@dataclass(frozen=True)
class Page:
    """One written page. ``slug`` is its URL under the root and the name
    of its file; ``title`` and ``description`` are what a search result
    shows. ``cta_path`` is the create page this one is an argument for,
    because a page that reads well and goes nowhere is a leaflet."""

    slug: str
    title: str
    description: str
    cta_path: str
    cta_label: str
    order: int
    body: str

    @cached_property
    def html(self) -> str:
        """The prose as HTML. Rendered on first read and kept, so the
        cost is paid once per process rather than per request."""
        _MARKDOWN.reset()
        return _MARKDOWN.convert(self.body)


def _parse(path: pathlib.Path) -> Page:
    """One file into one page. The front matter is ``key: value`` lines
    between two ``---`` fences: enough for five strings, and no YAML
    parser to keep current."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name}: no front matter")
    front, _, body = raw[4:].partition("\n---\n")
    meta: dict[str, str] = {}
    for line in front.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{path.name}: front-matter line without a colon: {line!r}")
        meta[key.strip()] = value.strip()
    missing = [key for key in _REQUIRED if key not in meta]
    if missing:
        raise ValueError(f"{path.name}: front matter is missing {', '.join(missing)}")
    return Page(
        slug=path.stem,
        title=meta["title"],
        description=meta["description"],
        cta_path=meta["cta_path"],
        cta_label=meta["cta_label"],
        order=int(meta["order"]),
        body=body.strip(),
    )


def _load() -> tuple[Page, ...]:
    pages = sorted((_parse(p) for p in CONTENT_DIR.glob("*.md")), key=lambda p: (p.order, p.slug))
    orders = [p.order for p in pages]
    if len(set(orders)) != len(orders):
        raise ValueError(f"two pages claim the same order: {sorted(orders)}")
    return tuple(pages)


PAGES: tuple[Page, ...] = _load()

BY_SLUG: dict[str, Page] = {page.slug: page for page in PAGES}
