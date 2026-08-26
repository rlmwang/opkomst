"""The pages that are read rather than used: the policy and the
written pages behind ``services/content.py``.

A plain server-rendered page rather than a route in the SPA, for one
reason that is not aesthetic. The consent dialog appears on every
house-brand page, and Google asks that the policy the dialog links to
sit on a path the dialog does not itself cover, so that "learn more"
does not land the reader back in front of the thing they were trying to
read about. A page outside the SPA loads no bundle, so it loads no ad
tag, so no dialog can appear on it.

It wears the brand by linking the same ``tokens.css`` every other page
links, and nothing else: no JavaScript at all.

Bilingual on one page rather than two URLs. The reader arrived from a
consent dialog in whichever language their device is set to, and a
policy is short enough that both fit; one URL is also one thing to
paste into the AdSense console and one thing to keep current.
"""

import pathlib

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..services import brand as brand_svc
from ..services import traffic
from ..services.content import BY_SLUG, PAGES

router = APIRouter(tags=["privacy"], include_in_schema=False)

_TEMPLATES = Jinja2Templates(directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates"))


_PUBLIC_BASE = str(settings.public_base_url).rstrip("/")


def _render(request: Request, template: str, **context: object) -> HTMLResponse:
    """One chrome for every page here: the brand, the footer built from
    the page list, and the canonical URL."""
    return _TEMPLATES.TemplateResponse(
        request,
        template,
        {
            "brand": brand_svc.payload(brand_svc.HOUSE_BRAND),
            "pages": PAGES,
            **context,
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _written_page(slug: str, request: Request) -> HTMLResponse:
    page = BY_SLUG[slug]
    traffic.record("content")
    # These are house-brand pages and they carry advertising, on the
    # terms in ``docs/ads.md``: rails at the window edges on a wide
    # screen, one banner at the foot of the page otherwise, nothing at
    # all until a network is configured. ``ads_allowed`` is what
    # ``SecurityHeadersMiddleware`` reads to pick the loosened policy,
    # and it stays false without a client id so an unconfigured
    # deployment keeps the strict one.
    #
    # ``/privacy`` next door deliberately gets none of this: Google's
    # consent dialog links there, and a dialog that reappears on the
    # page explaining it is the thing their policy is asking us to
    # avoid. ``tests/test_ads.py`` pins that.
    ads = brand_svc.payload(brand_svc.HOUSE_BRAND)["ads"]
    ads = ads if ads and ads["client_id"] else None
    request.state.ads_allowed = ads is not None
    return _render(
        request,
        f"content/{page.slug}.html",
        page=page,
        ads=ads,
        csp_nonce=request.state.csp_nonce,
        page_title=page.title,
        page_description=page.description,
        canonical_url=f"{_PUBLIC_BASE}/{page.slug}",
    )


# One route per page, not ``/{slug}``. A single-segment path parameter
# here would sit in front of the SPA fallback and swallow every
# one-segment URL in the app: ``/rsp``, ``/login``, ``/events``. Naming
# each path means only these four are taken.
for _page in PAGES:

    def _handler(request: Request, _slug: str = _page.slug) -> HTMLResponse:
        return _written_page(_slug, request)

    router.add_api_route(
        f"/{_page.slug}",
        _handler,
        methods=["GET", "HEAD"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )


@router.head("/privacy", include_in_schema=False)
@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    """The house brand's policy. Organisations using this app answer for
    their own processing under their own policy; what is described here
    is what this app does, which is the same in either case."""
    traffic.record("privacy")
    return _render(
        request,
        "privacy.html",
        contact_email=settings.privacy_contact_email,
        controller=settings.privacy_controller,
        page_title="Privacyverklaring",
        page_description=(
            "Wat opkomst.nu met gegevens doet: welke velden er gevraagd worden, "
            "hoe lang een e-mailadres bewaard blijft, en wie er verder iets ziet."
        ),
        canonical_url=f"{_PUBLIC_BASE}/privacy",
    )
