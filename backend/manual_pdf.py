"""The manual as PDF: one file per brand and language
(``docs/design-manual.md`` chapter 8).

    python -m backend.manual_pdf <out-dir>

Its own entry point and not a ``backend/cli.py`` subcommand: the CLI
builds ``Settings`` when it is imported and runs the migrations and
the tenant reconcile before any subcommand, and this runs in a Docker
build stage with no environment and no database. It imports the manual
service, the folder-reading half of the brand service, Jinja and
WeasyPrint, and nothing from ``config``; ``tests/test_imports.py``
keeps it that way.

WeasyPrint does paged media properly: page size and margins, a running
footer with the page number, a break before every chapter, and a table
of contents whose numbers the renderer computes (``target-counter``).
The pictures and the logo are read off disk through a URL fetcher that
maps the paths the web pages use onto the folders they come from.
"""

from __future__ import annotations

import datetime
import pathlib
import sys
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML  # type: ignore[import-untyped]
from weasyprint.urls import URLFetcher  # type: ignore[import-untyped]

from .services import brand as brand_svc
from .services import manual
from .services.manual import Audience

_TEMPLATES = Environment(
    loader=FileSystemLoader(str(pathlib.Path(__file__).resolve().parent / "templates")),
    autoescape=select_autoescape(),
)

_WORDS: dict[str, str] = {"nl": "handleiding", "en": "manual"}
_LABELS: dict[str, dict[str, str]] = {
    "nl": {"manual": "Handleiding", "contents": "Inhoud", "built": "Versie van"},
    "en": {"manual": "Manual", "contents": "Contents", "built": "Version of"},
}
_MONTHS = {
    "nl": [
        "januari",
        "februari",
        "maart",
        "april",
        "mei",
        "juni",
        "juli",
        "augustus",
        "september",
        "oktober",
        "november",
        "december",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
}


class _DiskFetcher(URLFetcher):  # type: ignore[misc]
    """Serve the page's own paths off disk: the manual's pictures from
    the language folder, a brand's files from ``brands/``. The page is
    rendered against ``file:///``, so ``/manual-pictures/nl/x.png``
    arrives here as ``file:///manual-pictures/nl/x.png``. Anything else
    goes the ordinary way, which for a build stage is nowhere."""

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> Any:
        if url.startswith("file:///manual-pictures/"):
            language, name = url[len("file:///manual-pictures/") :].split("/", 1)
            path = manual.picture_path(language, name.removesuffix(".png"))
        elif url.startswith("file:///brand/"):
            path = brand_svc.BRANDS_DIR / url[len("file:///brand/") :]
        else:
            return super().fetch(url, headers)
        if ".." in path.parts or not path.is_file():
            raise FileNotFoundError(url)
        return super().fetch(path.resolve().as_uri(), headers)


def document(brand_slug: str, language: str, built: datetime.date) -> Any:
    """The laid-out book, before it is written: the audience is the
    brand's, the house brand being the personal app and every other
    brand an organisation. A test counts its pages here."""
    audience: Audience = "all" if brand_slug == brand_svc.HOUSE_BRAND else "organisation"
    chapters = manual.chapters_for(language, audience)
    manifest = brand_svc.manifest(brand_slug)
    html = _TEMPLATES.get_template("manual-print.html").render(
        language=language,
        labels=_LABELS[language],
        wordmark=manifest["wordmark"],
        app_name=manifest["app_name"],
        logo_url=brand_svc.asset_url(brand_slug, manifest["logo"]) if manifest["logo"] else None,
        palette_css=brand_svc.palette_css(brand_slug),
        chapters=[(c, c.html_for(audience)) for c in chapters],
        built=f"{_MONTHS[language][built.month - 1]} {built.year}",
    )
    return HTML(string=html, base_url="file:///", url_fetcher=_DiskFetcher()).render()


def render(brand_slug: str, language: str, built: datetime.date) -> bytes:
    """One PDF."""
    return document(brand_slug, language, built).write_pdf()


def build(out: pathlib.Path, built: datetime.date | None = None) -> list[pathlib.Path]:
    """Every committed brand in every language. The house brand's files
    are written at the root of ``out`` as well, since the root serves
    them without a prefix."""
    built = built or datetime.date.today()
    written: list[pathlib.Path] = []
    for folder in sorted(p for p in brand_svc.BRANDS_DIR.iterdir() if (p / "brand.json").is_file()):
        for language, word in _WORDS.items():
            pdf = render(folder.name, language, built)
            target = out / folder.name / f"{word}.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(pdf)
            written.append(target)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m backend.manual_pdf <out-dir>", file=sys.stderr)
        return 2
    for path in build(pathlib.Path(argv[1])):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
