"""Rich-text sanitization for organiser-authored bodies.

The single chokepoint for the formatted "details" field (the event
``topic``, the form / datepoll / roster ``description``). Every write
funnels through :func:`sanitize_richtext` at the schema boundary
(``schemas.common.RichText``), so nothing an organiser types can become
executable markup on a public page: the output is restricted to a closed
allowlist of inline marks plus safe links, and is rendered with
``v-html`` downstream on the strength of that guarantee.

:func:`html_to_text` is the inverse for the plaintext surfaces that
cannot take HTML (Open Graph meta, the ICS ``DESCRIPTION``, the reminder
email), plus the visible-length gate.
"""

from html.parser import HTMLParser

import nh3

# The five requested marks (bold / italic / underline / strikethrough /
# link) plus the block tags an editor emits for paragraphs and breaks.
# Nothing else survives: no headings, images, lists, spans, styles.
_ALLOWED_TAGS = {"p", "br", "strong", "em", "u", "s", "a"}

# Only ``href`` on ``<a>``. No ``style`` / ``class`` / ``id`` / ``on*``.
_ALLOWED_ATTRS = {"a": {"href"}}

# ``javascript:`` / ``data:`` / ``vbscript:`` hrefs are dropped.
_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}

# Forced on every surviving link: no ``window.opener`` hijack, no
# referrer leak, no pagerank pass-through from user content.
_LINK_REL = "nofollow noopener noreferrer"

# ``<script>`` / ``<style>`` have their *contents* removed too, not just
# the tag unwrapped, so no inert-looking text smuggles script through.
_CLEAN_CONTENT_TAGS = {"script", "style"}

# Cap on the *visible* text (what a reader sees), the number organisers
# reason about. Markup does not count against it; the raw-HTML ceiling
# lives on the ``RichText`` field itself.
VISIBLE_MAX_LENGTH = 2000


def sanitize_richtext(value: str | None) -> str | None:
    """Strip an HTML body to the allowlisted inline marks + safe links.

    Idempotent and total: re-sanitizing clean output is a no-op, and
    there is no configuration under which disallowed tags, attributes,
    or URL schemes survive. Empty / whitespace-only input collapses to
    ``None`` so an empty editor stores nothing.
    """
    if value is None:
        return None
    cleaned = nh3.clean(
        value,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_ALLOWED_URL_SCHEMES,
        link_rel=_LINK_REL,
        clean_content_tags=_CLEAN_CONTENT_TAGS,
    ).strip()
    # Markup with no visible text (an editor left with only empty
    # paragraphs / a stray <br>) stores nothing.
    if not cleaned or not html_to_text(cleaned):
        return None
    return cleaned


class _TextExtractor(HTMLParser):
    """Collapse allowlisted HTML back to readable plain text: unwrap
    tags, turn ``<br>`` and paragraph boundaries into newlines, decode
    entities (``HTMLParser`` hands us already-unescaped data)."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: object) -> None:
        if tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            self._parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(value: str | None) -> str:
    """Flatten a sanitized rich-text body to plain text for the surfaces
    that can't render HTML (OG meta, ICS, email). Returns ``""`` for
    ``None``; collapses the runs of blank lines paragraphs introduce."""
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    lines = [line.rstrip() for line in parser.text().splitlines()]
    # Collapse 3+ newlines (empty lines) down to a single blank line.
    out: list[str] = []
    blank = False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()
