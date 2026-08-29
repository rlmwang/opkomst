"""The written pages, and the guards that keep them findable.

Everything here is a rule from ``docs/seo.md`` that would break
silently: a page that stops being served, a title that goes back to
being the same on every URL, an event page that starts appearing in
search results, or a footer whose links rot because the list moved.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from backend.services.content import BY_SLUG, PAGES
from backend.services.slug import RESERVED_SLUGS

_FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"
_FOOTER = _FRONTEND / "src" / "public_shared" / "Colophon.vue"
_VITE_CONFIG = _FRONTEND / "vite.config.ts"


@pytest.mark.parametrize("page", PAGES, ids=[p.slug for p in PAGES])
def test_each_written_page_is_served_and_describes_itself(client, page) -> None:
    """A page written to be found has to be readable in the HTML that
    arrives, with its own title, description and canonical."""
    response = client.get(f"/{page.slug}")
    assert response.status_code == 200
    body = response.text
    assert page.title in body
    assert f'<meta name="description" content="{page.description}">' in body
    assert '<link rel="canonical" href="' in body
    # It points at the thing in the app that solves the problem it
    # describes. A page that reads well and goes nowhere is a leaflet.
    assert page.cta_path in body


@pytest.mark.parametrize("page", PAGES, ids=[p.slug for p in PAGES])
def test_a_written_page_loads_nothing_without_a_network(client, page) -> None:
    """No bundle either way, and with no ``ADSENSE_CLIENT_ID`` no script
    at all: nothing runs before the text is readable, and nothing can
    put a consent dialog in front of it. What a configured deployment
    adds is pinned in ``tests/test_ads.py``."""
    body = client.get(f"/{page.slug}").text
    assert "<script" not in body.lower() or "application/ld+json" in body
    assert "googlesyndication" not in body


def test_the_written_slugs_cannot_be_taken_by_a_chapter() -> None:
    """These are top-level paths. An organisation or a chapter named
    after one would shadow it."""
    for page in PAGES:
        assert page.slug in RESERVED_SLUGS, page.slug


def test_the_footer_list_matches_the_server(client) -> None:
    """The frontend keeps its own copy of the page list, because the
    alternative was shipping it through the brand payload and making
    brand data out of something that is not. This is what stops the
    copy from rotting."""
    source = _FOOTER.read_text(encoding="utf-8")
    slugs = re.findall(r'slug: "([^"]+)"', source)
    titles = re.findall(r'title: "([^"]+)"', source)
    assert slugs == [p.slug for p in PAGES]
    assert titles == [p.title for p in PAGES]


def test_the_sitemap_lists_what_should_be_indexed(client) -> None:
    body = client.get("/sitemap.xml").text
    for path in ("/event/new", "/form/new", "/datepoll/new", "/chore/new", "/privacy"):
        assert "<loc>" in body and path in body, path
    for page in PAGES:
        assert page.slug in body, page.slug
    # Not an event, a form or a roster: those expire and are noindex.
    assert "/e/" not in body


def test_robots_points_at_the_sitemap(client) -> None:
    assert "Sitemap:" in client.get("/robots.txt").text


@pytest.mark.parametrize(
    ("path", "expected"),
    [("/", 200), ("/event/new", 200), ("/privacy", 200), ("/nope-not-a-page", 404)],
)
def test_a_path_nothing_serves_is_a_404(client, path: str, expected: int) -> None:
    """A soft 404 is a 200 on a page that does not exist. Google flags
    them and keeps crawling them, and the app's own vocabulary is what
    tells the two apart."""
    assert client.get(path).status_code == expected


@pytest.mark.parametrize("prefix", ["e", "f", "d", "c"])
def test_an_unknown_slug_is_a_404_not_a_page(client, prefix: str) -> None:
    """The server resolved it to nothing, so it knows."""
    assert client.get(f"/{prefix}/nosuchslug").status_code == 404


def test_the_five_app_pages_describe_themselves(client) -> None:
    """One title on five URLs is a search engine with five pages it
    cannot tell apart."""
    titles = {}
    for path in ("/", "/event/new", "/form/new", "/datepoll/new", "/chore/new"):
        head = client.get(path).text.split("</head>")[0]
        match = re.search(r"<title>(.*?)</title>", head)
        assert match, path
        titles[path] = match.group(1)
        assert 'name="description"' in head, path
        assert '<link rel="canonical"' in head, path
        # The tag, not the word: the shell carries a comment about
        # ``noindex`` explaining when it is emitted.
        assert 'name="robots"' not in head, path
    assert len(set(titles.values())) == len(titles), titles


def test_the_organiser_app_is_not_described_to_a_crawler(client) -> None:
    """A dashboard behind a sign-in has no business in an index."""
    head = client.get("/rsp/event").text.split("</head>")[0]
    assert 'content="noindex, follow"' in head


def test_the_root_carries_structured_data(client) -> None:
    body = client.get("/").text
    assert "application/ld+json" in body
    assert "WebApplication" in body


def test_a_page_is_reachable_from_its_own_footer(client) -> None:
    """Every written page links to every other one, so a crawler that
    lands on any of them finds the rest without going through the
    root."""
    body = client.get(f"/{PAGES[0].slug}").text
    for page in PAGES[1:]:
        assert f'/{page.slug}"' in body, page.slug
    assert '/privacy"' in body


def test_by_slug_covers_every_page() -> None:
    assert set(BY_SLUG) == {p.slug for p in PAGES}


def test_the_dev_server_proxies_every_written_page() -> None:
    """These paths are rendered by the backend, so Vite has to forward
    them. A slug missing here is a link that works in production and
    dies in dev, which is the one place it will be clicked while the
    page is being written."""
    source = _VITE_CONFIG.read_text(encoding="utf-8")
    block = source.split("const CONTENT_PATHS = [", 1)[1].split("]", 1)[0]
    proxied = re.findall(r'"([^"]+)"', block)
    # The two pages that are read rather than used come first, then the
    # written pages in the order ``services/content.py`` lists them.
    assert proxied == ["/privacy", "/voorwaarden", *(f"/{p.slug}" for p in PAGES)]


def test_every_page_is_one_markdown_file_with_complete_front_matter() -> None:
    """A page is a file in ``backend/content``. The loader refuses a
    file that is missing a front-matter key, so this asserts the shape
    the loader produced rather than re-parsing it: every page has the
    five fields, a body, and a unique place in the order."""
    from backend.services.content import CONTENT_DIR

    files = sorted(p.stem for p in CONTENT_DIR.glob("*.md"))
    assert files == sorted(p.slug for p in PAGES)
    for page in PAGES:
        assert page.title and page.description and page.cta_label
        assert page.cta_path.startswith("/")
        assert page.body.strip()
        # Rendered markdown, not the source: a page that renders to
        # nothing would still have passed every check above.
        assert "<p>" in page.html
    assert len({p.order for p in PAGES}) == len(PAGES)
