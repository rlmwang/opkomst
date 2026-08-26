"""``/privacy``: the privacy policy, served outside the app.

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

router = APIRouter(tags=["privacy"], include_in_schema=False)

_TEMPLATES = Jinja2Templates(directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates"))


@router.head("/privacy", include_in_schema=False)
@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    """The house brand's policy. Organisations using this app answer for
    their own processing under their own policy; what is described here
    is what this app does, which is the same in either case."""
    return _TEMPLATES.TemplateResponse(
        request,
        "privacy.html",
        {
            "brand": brand_svc.payload(brand_svc.HOUSE_BRAND),
            "contact_email": settings.privacy_contact_email,
            "controller": settings.privacy_controller,
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )
