"""The manual (``docs/design-manual.md``): fourteen chapters in two
languages, one markdown file each, rendered on first read.

Mirrors ``services/content.py`` without merging with it. A written
page has a call to action and one language; a chapter has an audience
and two languages. What they share, the front-matter parser, is
``services/frontmatter.py``.

**The audience is the tenant.** A chapter is for everybody or for an
organisation, by its front matter; the last three are the
organisation's. Where an organisation's screen differs inside a chapter
everybody reads, the door's name step, the form's chapter picker, the
paragraph is marked ``{: .organisation }`` and the root rendering drops
it. Only a paragraph may be marked: the drop is done on the rendered
HTML, one ``<p>`` at a time, and ``tests/test_manual.py`` checks that
nothing marked survives it.

**Pictures** are named in the markdown by the tour, product and step
they were shot from, with no path and no extension
(``![caption](lijst.event.2)``), and resolved to that language's folder
at render time. A reference to a picture that is not on disk fails the
suite, never a reader. The shooting script writes every step of every
tour, and a chapter names the ones it needs; the rest are on disk for
the chapter that will.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

import markdown

from .frontmatter import parse

MANUAL_DIR = pathlib.Path(__file__).resolve().parent.parent / "manual"
LANGUAGES: tuple[str, ...] = ("nl", "en")
_REQUIRED = ("title", "description", "audience")
_MARKDOWN = markdown.Markdown(extensions=["tables", "attr_list"])

Audience = Literal["all", "organisation"]
ORGANISATION_CLASS = "organisation"

# ``NN-slug.md``: the number is the order and nothing else reads it.
_NAME = re.compile(r"^(\d{2})-([a-z0-9-]+)\.md$")
# A picture reference: ``![caption](tour.product.step)``, no slash, no dot
# extension a browser would recognise. Anything with a slash or a scheme is
# an ordinary link and is left alone.
_PICTURE = re.compile(r"!\[([^\]]*)\]\(([a-z][a-z0-9.-]*)\)")
# The same reference once the markdown renderer has placed it, alone in
# its paragraph, inside a list item or not.
_PICTURE_HTML = re.compile(r'<p><img alt="([^"]*)" src="([a-z][a-z0-9.-]*)" /></p>')
# A paragraph the markdown renderer tagged for the organisation.
_ORGANISATION_P = re.compile(
    r'<p class="(?:[^"]*\s)?' + ORGANISATION_CLASS + r'(?:\s[^"]*)?">.*?</p>\s*',
    re.S,
)


@dataclass(frozen=True)
class Chapter:
    """One chapter in one language. ``number`` is its place in the
    book; ``slug`` is its address under ``/handleiding`` or
    ``/manual``."""

    language: str
    number: int
    slug: str
    title: str
    description: str
    audience: Audience
    body: str

    @cached_property
    def pictures(self) -> tuple[str, ...]:
        """Every picture the chapter names, in order."""
        return tuple(m.group(2) for m in _PICTURE.finditer(self.body))

    @cached_property
    def html(self) -> str:
        """The prose as HTML, for every audience. Rendered on first read
        and kept, so the cost is paid once per process. A picture is
        turned into a figure after the renderer has placed it, so one
        that sits inside a step stays inside that step."""
        _MARKDOWN.reset()
        html = _MARKDOWN.convert(self.body)
        return _PICTURE_HTML.sub(
            lambda m: (
                f'<figure><img src="{picture_url(self.language, m.group(2))}" alt="{m.group(1)}">'
                f"<figcaption>{m.group(1)}</figcaption></figure>"
            ),
            html,
        )

    def html_for(self, audience: Audience) -> str:
        """The prose for one audience: the root drops every paragraph
        marked for the organisation."""
        if audience == "organisation":
            return self.html
        return _ORGANISATION_P.sub("", self.html)


def picture_url(language: str, name: str) -> str:
    return f"/manual-pictures/{language}/{name}.png"


def picture_path(language: str, name: str) -> pathlib.Path:
    return MANUAL_DIR / language / "pictures" / f"{name}.png"


def _parse(language: str, path: pathlib.Path) -> Chapter:
    found = _NAME.match(path.name)
    if not found:
        raise ValueError(f"{language}/{path.name}: a chapter is named NN-slug.md")
    meta, body = parse(path, _REQUIRED)
    if meta["audience"] not in ("all", "organisation"):
        raise ValueError(f"{language}/{path.name}: audience is all or organisation")
    return Chapter(
        language=language,
        number=int(found.group(1)),
        slug=found.group(2),
        title=meta["title"],
        description=meta["description"],
        audience=meta["audience"],  # type: ignore[arg-type]
        body=body,
    )


def _load(language: str) -> tuple[Chapter, ...]:
    chapters = sorted((_parse(language, p) for p in (MANUAL_DIR / language).glob("*.md")), key=lambda c: c.number)
    numbers = [c.number for c in chapters]
    if len(set(numbers)) != len(numbers):
        raise ValueError(f"{language}: two chapters claim the same number: {numbers}")
    return tuple(chapters)


CHAPTERS: dict[str, tuple[Chapter, ...]] = {language: _load(language) for language in LANGUAGES}

# Both languages are one book: the same numbers, the same audiences.
for _language in LANGUAGES[1:]:
    _first = [(c.number, c.audience) for c in CHAPTERS[LANGUAGES[0]]]
    _other = [(c.number, c.audience) for c in CHAPTERS[_language]]
    if _first != _other:
        raise ValueError(f"{LANGUAGES[0]} and {_language} do not hold the same chapters: {_first} vs {_other}")


def chapters_for(language: str, audience: Audience) -> tuple[Chapter, ...]:
    """The table of contents for one audience: the root leaves the
    organisation's chapters out. They are the last ones, so a number
    means the same chapter in both."""
    return tuple(c for c in CHAPTERS[language] if audience == "organisation" or c.audience == "all")


def by_slug(language: str, slug: str) -> Chapter | None:
    return next((c for c in CHAPTERS[language] if c.slug == slug), None)
