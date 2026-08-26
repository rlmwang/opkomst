"""The written pages: what they are, where they live, and their order.

Five pages of forms is a thin site, and no amount of metadata fixes
that (``docs/seo.md`` part 3). These are the pages that answer the
question somebody actually types, and each one ends by pointing at the
thing in the app that solves it.

Server-rendered rather than routes in the SPA, for the same reason
``/privacy`` is: a page written to be found should be readable in the
HTML that arrives, not after a bundle has loaded and rendered. They
also load no JavaScript at all, which keeps them fast and keeps the ad
tag off them.

This module is the single list. The router serves from it, the sitemap
is generated from it, the footer is built from it, and
``tests/test_content.py`` checks the frontend's copy of the list still
agrees with it. Adding a page means adding an entry and a template.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    """One written page. ``slug`` is its URL under the root and the
    name of its template; ``title`` and ``description`` are what a
    search result shows."""

    slug: str
    title: str
    description: str
    # What the footer calls it. The title is a sentence because a
    # search result is read as one; a colophon of six sentences is a
    # wall, so the same page gets a two-word name where it is only
    # being pointed at.
    label: str
    # The create page this one is an argument for. Every written page
    # ends by pointing at the thing that solves the problem it
    # describes; a page that reads well and goes nowhere is a leaflet.
    cta_path: str
    cta_label: str


PAGES: tuple[Page, ...] = (
    Page(
        slug="datumprikker-zonder-account",
        label="Datumprikker",
        title="Datumprikker zonder account of cookies",
        description=(
            "Een datum prikken met een groep, zonder dat iemand een account maakt "
            "en zonder cookies. Wat andere datumprikkers opslaan, en wat wij niet doen."
        ),
        cta_path="/datepolls/new",
        cta_label="Maak een datumprikker",
    ),
    Page(
        slug="aanmeldformulier-zonder-google",
        label="Aanmeldformulier",
        title="Aanmeldformulier maken zonder Google Forms",
        description=(
            "Een aanmeldformulier voor je evenement zonder Google-account en zonder "
            "dat de antwoorden bij een advertentiebedrijf terechtkomen."
        ),
        cta_path="/forms/new",
        cta_label="Maak een vragenlijst",
    ),
    Page(
        slug="wat-gebeurt-er-met-je-mailadres",
        label="E-mailadressen",
        title="Wat er met je e-mailadres gebeurt",
        description=(
            "Versleuteld opgeslagen, gebruikt voor de mails die de organisator "
            "aanzette, en daarna gewist. Wat dat precies betekent, stap voor stap."
        ),
        cta_path="/events/new",
        cta_label="Maak een evenement",
    ),
    Page(
        slug="vrijwilligers-inroosteren",
        label="Vrijwilligersrooster",
        title="Vrijwilligers inroosteren zonder spreadsheet",
        description=(
            "Een terugkerend rooster waarin de beurten eerlijk rondgaan, zonder "
            "dat iemand elke week een spreadsheet bijwerkt."
        ),
        cta_path="/chores/new",
        cta_label="Maak een rooster",
    ),
)

BY_SLUG: dict[str, Page] = {page.slug: page for page in PAGES}
