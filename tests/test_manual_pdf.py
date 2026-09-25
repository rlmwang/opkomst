"""The manual's PDF build (``backend/manual_pdf.py``): one file per
brand and language, more pages than chapters, the organisation's with
three chapters more. Needs WeasyPrint and Pango, which CI installs and
a laptop may not; without them the test is skipped, never failed."""

from __future__ import annotations

import datetime
import pathlib

import pytest

pytest.importorskip("weasyprint")

from backend import manual_pdf  # noqa: E402
from backend.services import brand as brand_svc  # noqa: E402
from backend.services import manual  # noqa: E402


def test_the_build_writes_a_file_per_brand_and_language(tmp_path: pathlib.Path) -> None:
    written = manual_pdf.build(tmp_path, built=datetime.date(2026, 9, 1))
    brands = sorted(p.name for p in brand_svc.BRANDS_DIR.iterdir() if (p / "brand.json").is_file())
    assert sorted(str(p.relative_to(tmp_path)) for p in written) == sorted(
        f"{b}/{w}.pdf" for b in brands for w in ("handleiding", "manual")
    )
    for path in written:
        assert path.read_bytes().startswith(b"%PDF"), path


def test_the_house_brand_has_the_root_book_and_an_organisation_three_chapters_more() -> None:
    built = datetime.date(2026, 9, 1)
    house = manual_pdf.document(brand_svc.HOUSE_BRAND, "nl", built)
    org = manual_pdf.document("rsp", "nl", built)
    root_chapters = len(manual.chapters_for("nl", "all"))
    # A cover, a table of contents, and a page per chapter at least.
    assert len(house.pages) >= root_chapters + 2
    assert len(org.pages) >= len(house.pages) + 3
    assert house.write_pdf()[:4] == b"%PDF"
