"""The written pages: what they are, where they live, and their order.

Five pages of forms is a thin site, and no amount of metadata fixes
that (``docs/seo.md`` part 3). These are the pages that answer the
question somebody actually types, and each one ends by pointing at the
thing in the app that solves it.

Server-rendered rather than routes in the SPA, for the same reason
``/privacy`` is: a page written to be found should be readable in the
HTML that arrives, not after a bundle has loaded and rendered. The text
is on screen before anything else runs, including the ad tag these
pages carry (``docs/ads.md``); the policy page next door carries none.

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
    # The create page this one is an argument for. Every written page
    # ends by pointing at the thing that solves the problem it
    # describes; a page that reads well and goes nowhere is a leaflet.
    cta_path: str
    cta_label: str


PAGES: tuple[Page, ...] = (
    Page(
        slug="aanmeldpagina-voor-je-evenement",
        title="Aanmeldpagina voor je evenement, zonder kosten per aanmelding",
        description=(
            "Een aanmeldpagina voor je evenement met één link: naam, aantal personen, "
            "en hooguit twee mails. Geen ticketkosten en geen kosten per aanmelding."
        ),
        cta_path="/events/new",
        cta_label="Maak een evenement",
    ),
    Page(
        slug="datumplanner-zonder-account",
        title="Datumplanner zonder account of cookies",
        description=(
            "Een datum prikken met een groep, zonder dat iemand een account maakt "
            "en zonder cookies. Wat andere datumplanners opslaan, en wat wij niet doen."
        ),
        cta_path="/datepolls/new",
        cta_label="Maak een datumplanner",
    ),
    Page(
        slug="aanmeldformulier-zonder-google",
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
        title="Wat er met je e-mailadres gebeurt",
        description=(
            "Versleuteld opgeslagen, gebruikt voor de mails die de organisator "
            "aanzette, en daarna gewist. Wat dat precies betekent, stap voor stap."
        ),
        cta_path="/events/new",
        cta_label="Maak een evenement",
    ),
    Page(
        slug="pubquiz-maken-zonder-account",
        title="Pubquiz maken zonder account of abonnement",
        description=(
            "Een pubquiz maken en spelen zonder dat deelnemers een account maken en "
            "zonder abonnement. Vragen met punten, scores meteen na afloop."
        ),
        cta_path="/quizzes/new",
        cta_label="Maak een quiz",
    ),
    Page(
        slug="kieskompas-maken-zonder-onderzoeksbureau",
        title="Een kieskompas maken voor je eigen groep",
        description=(
            "Twee assen die je zelf benoemt, een stuk of tien stellingen en één link. "
            "Iedereen ziet waar diegene staat en waar de groep staat."
        ),
        cta_path="/compasses/new",
        cta_label="Maak een kompas",
    ),
    Page(
        slug="vrijwilligers-inroosteren",
        title="Vrijwilligers inroosteren zonder spreadsheet",
        description=(
            "Een terugkerend rooster waarin de beurten eerlijk rondgaan, zonder "
            "dat iemand elke week een spreadsheet bijwerkt."
        ),
        cta_path="/chores/new",
        cta_label="Maak een rooster",
    ),
    Page(
        slug="wat-mag-je-bewaren-van-deelnemers",
        title="Wat mag je bewaren van je deelnemers?",
        description=(
            "Vraag niet meer dan je nodig hebt, zeg waarvoor je het gebruikt, en "
            "bewaar het niet langer dan dat. Wat dat betekent voor een aanmeldlijst."
        ),
        cta_path="/events/new",
        cta_label="Maak een evenement",
    ),
    Page(
        slug="ledenvergadering-voorbereiden",
        title="Een ledenvergadering voorbereiden",
        description=(
            "Een datum kiezen, weten wie er komt, de stemming peilen en achteraf "
            "vragen hoe het ging. Vier stappen, vier links."
        ),
        cta_path="/datepolls/new",
        cta_label="Maak een datumplanner",
    ),
    Page(
        slug="gratis-alternatief-voor-eventbrite",
        title="Gratis alternatief voor Eventbrite",
        description=(
            "Voor een bijeenkomst zonder kaartverkoop: één aanmeldlink, geen account "
            "voor je bezoekers, en geen marktplaats die ze daarna zelf mailt."
        ),
        cta_path="/events/new",
        cta_label="Maak een evenement",
    ),
)

BY_SLUG: dict[str, Page] = {page.slug: page for page in PAGES}
