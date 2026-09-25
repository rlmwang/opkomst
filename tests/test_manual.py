"""The manual (``services/manual.py``): fourteen chapters in two
languages, an audience per chapter and per paragraph, and pictures
that are on disk or fail here."""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from backend.services import manual
from backend.services.manual import Chapter, picture_path
from backend.services.slug import RESERVED_SLUGS


def _chapter(body: str, audience: str = "all") -> Chapter:
    return Chapter(
        language="nl",
        number=1,
        slug="proef",
        title="Proef",
        description="Een proefhoofdstuk.",
        audience=audience,  # type: ignore[arg-type]
        body=textwrap.dedent(body).strip(),
    )


def test_both_languages_hold_the_same_book() -> None:
    nl = [(c.number, c.audience) for c in manual.CHAPTERS["nl"]]
    en = [(c.number, c.audience) for c in manual.CHAPTERS["en"]]
    assert nl == en
    assert len(nl) == 14
    assert [c.number for c in manual.CHAPTERS["nl"]] == list(range(1, 15))


def test_the_root_leaves_the_organisation_chapters_out_and_they_are_last() -> None:
    for language in manual.LANGUAGES:
        root = manual.chapters_for(language, "all")
        org = manual.chapters_for(language, "organisation")
        assert all(c.audience == "all" for c in root)
        assert len(org) == len(root) + 3
        assert [c.audience for c in org[-3:]] == ["organisation"] * 3
        # The same number is the same chapter in both.
        assert [c.number for c in root] == [c.number for c in org[: len(root)]]


@pytest.mark.parametrize("language", manual.LANGUAGES)
def test_every_chapter_opens_with_two_sentences_and_a_description(language: str) -> None:
    for chapter in manual.CHAPTERS[language]:
        assert chapter.title and chapter.description, chapter.slug
        first = chapter.body.split("\n\n")[0]
        assert 1 <= len([s for s in first.replace("? ", ". ").split(". ") if s.strip()]) <= 3, (
            chapter.slug,
            first,
        )


def test_a_paragraph_marked_for_the_organisation_is_dropped_at_the_root() -> None:
    chapter = _chapter(
        """
        Voor iedereen.

        Alleen voor een organisatie.
        {: .organisation }

        Weer voor iedereen.
        """
    )
    org = chapter.html_for("organisation")
    root = chapter.html_for("all")
    assert "Alleen voor een organisatie" in org
    assert "Alleen voor een organisatie" not in root
    assert manual.ORGANISATION_CLASS not in root
    assert "Voor iedereen" in root and "Weer voor iedereen" in root


def test_a_picture_reference_becomes_a_figure_with_its_caption() -> None:
    chapter = _chapter("Kijk hier.\n\n![De knop Opslaan](formulier.event.5)\n")
    assert chapter.pictures == ("formulier.event.5",)
    html = chapter.html
    assert 'src="/manual-pictures/nl/formulier.event.5.png"' in html
    assert 'alt="De knop Opslaan"' in html
    assert "<figcaption>De knop Opslaan</figcaption>" in html


def test_an_ordinary_link_is_not_a_picture() -> None:
    chapter = _chapter("Lees [het beleid](/privacy) en ![een plaatje](https://example.org/x.png).")
    assert chapter.pictures == ()


@pytest.mark.parametrize("language", manual.LANGUAGES)
def test_every_picture_a_chapter_names_is_on_disk(language: str) -> None:
    for chapter in manual.CHAPTERS[language]:
        for name in chapter.pictures:
            assert picture_path(language, name).is_file(), f"{language}/{chapter.slug} names {name}"


@pytest.mark.parametrize("language", manual.LANGUAGES)
def test_every_picture_on_disk_is_named_by_a_chapter(language: str) -> None:
    named = {name for chapter in manual.CHAPTERS[language] for name in chapter.pictures}
    on_disk = {p.stem for p in (manual.MANUAL_DIR / language / "pictures").glob("*.png")}
    assert on_disk <= named, f"{language}: orphaned pictures {sorted(on_disk - named)}"


def test_by_slug_finds_a_chapter_and_nothing_else() -> None:
    assert manual.by_slug("nl", "inloggen") is not None
    assert manual.by_slug("en", "signing-in") is not None
    assert manual.by_slug("nl", "signing-in") is None


def test_the_manual_words_cannot_be_taken_by_an_organisation_or_a_chapter() -> None:
    for word in ("handleiding", "manual", "manual-pictures", "q", "i"):
        assert word in RESERVED_SLUGS, word


def test_a_malformed_chapter_fails_at_import(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "01-slecht.md"
    bad.write_text("---\ntitle: Slecht\n---\nGeen audience.\n")
    with pytest.raises(ValueError, match="missing"):
        manual._parse("nl", bad)
    odd = tmp_path / "slecht.md"
    odd.write_text("---\ntitle: x\ndescription: y\naudience: all\n---\n")
    with pytest.raises(ValueError, match="NN-slug"):
        manual._parse("nl", odd)
    wrong = tmp_path / "02-fout.md"
    wrong.write_text("---\ntitle: x\ndescription: y\naudience: iedereen\n---\n")
    with pytest.raises(ValueError, match="audience"):
        manual._parse("nl", wrong)
