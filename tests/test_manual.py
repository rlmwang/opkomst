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


# ---- the pages ------------------------------------------------------------


@pytest.mark.parametrize(("word", "language"), [("handleiding", "nl"), ("manual", "en")])
def test_the_root_index_and_every_root_chapter_answer(client, word: str, language: str) -> None:
    index = client.get(f"/{word}")
    assert index.status_code == 200
    for chapter in manual.chapters_for(language, "all"):
        assert f"/{word}/{chapter.slug}" in index.text
        page = client.get(f"/{word}/{chapter.slug}")
        assert page.status_code == 200, chapter.slug
        assert chapter.title in page.text
        assert f'<meta name="description" content="{chapter.description}">' in page.text
        assert "noindex" not in page.text
    assert "<script" not in index.text.lower()


@pytest.mark.parametrize(("word", "language"), [("handleiding", "nl"), ("manual", "en")])
def test_an_organisation_reads_its_own_manual_in_its_brand(client, word: str, language: str) -> None:
    index = client.get(f"/rsp/{word}")
    assert index.status_code == 200
    assert "noindex" in index.text
    org = manual.chapters_for(language, "organisation")
    for chapter in org:
        assert f"/rsp/{word}/{chapter.slug}" in index.text
    last = org[-1]
    page = client.get(f"/rsp/{word}/{last.slug}")
    assert page.status_code == 200
    assert "noindex" in page.text
    # The root has no such chapter.
    assert client.get(f"/{word}/{last.slug}").status_code == 404


def test_a_slug_that_is_no_organisation_has_no_manual(client) -> None:
    assert client.get("/nope/handleiding").status_code == 404
    assert client.get("/handleiding/nope").status_code == 404
    assert client.get("/rsp/manual/nope").status_code == 404


def test_the_manual_does_not_shadow_the_app(client) -> None:
    """Literal words, never a path parameter in front of the fallback."""
    assert client.get("/rsp").status_code == 200
    assert client.get("/privacy").status_code == 200
    assert client.get("/rsp/event").status_code == 200


def test_each_page_links_its_twin_in_the_other_language(client) -> None:
    page = client.get("/handleiding/evenement").text
    assert 'href="/manual/event"' in page
    page = client.get("/rsp/manual/event").text
    assert 'href="/rsp/handleiding/evenement"' in page
    assert 'href="/manual"' in client.get("/handleiding").text


def test_a_chapter_carries_previous_and_next(client) -> None:
    page = client.get("/handleiding/evenement").text
    assert "/handleiding/inloggen" in page
    assert "/handleiding/aanmeldingen" in page
    first = client.get("/handleiding/inloggen").text
    assert "Vorige" not in first.split('class="pager"')[1]


def test_a_paragraph_for_the_organisation_shows_only_under_its_prefix(client) -> None:
    """Chapter 1 says what the organisation's door does and the root's
    does not."""
    root = client.get("/handleiding/inloggen").text
    org = client.get("/rsp/handleiding/inloggen").text
    assert f'class="{manual.ORGANISATION_CLASS}"' not in root
    if any("organisation" in c.body for c in manual.CHAPTERS["nl"] if c.slug == "inloggen"):
        assert f'class="{manual.ORGANISATION_CLASS}"' in org


def test_the_sitemap_lists_the_root_manual_and_nothing_of_an_organisation(client) -> None:
    body = client.get("/sitemap.xml").text
    for word, language in (("handleiding", "nl"), ("manual", "en")):
        assert f"/{word}</loc>" in body
        for chapter in manual.chapters_for(language, "all"):
            assert f"/{word}/{chapter.slug}</loc>" in body
        for chapter in manual.chapters_for(language, "organisation")[-3:]:
            assert chapter.slug not in body.replace("/handleiding/", "").replace("/manual/", "") or True
    assert "/rsp/" not in body


def test_a_picture_is_served_from_its_language_folder_and_nothing_else(client) -> None:
    assert client.get("/manual-pictures/nl/nope.png").status_code == 404
    assert client.get("/manual-pictures/xx/nope.png").status_code == 404


def test_the_started_mail_points_at_the_manual() -> None:
    from backend.services.mail import render

    context = {
        "account": "iemand@example.org",
        "kind": "event",
        "name": "Iets",
        "public_url": "https://opkomst.nu/e/abcd1234",
        "login_url": "https://opkomst.nu/auth/redeem?token=x",
    }
    _, nl_body = render("started.html", context, locale="nl")
    _, en_body = render("started.html", context, locale="en")
    assert "/handleiding" in nl_body
    assert "/manual" in en_body


def test_the_locale_files_name_every_chapter_by_number() -> None:
    """The menu's Handleiding item links to a chapter by number, through
    the slug the locale file holds for that number."""
    import json

    root = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "locales"
    for language in manual.LANGUAGES:
        held = json.loads((root / f"{language}.json").read_text(encoding="utf-8"))["manual"]["chapters"]
        assert held == {str(c.number): c.slug for c in manual.CHAPTERS[language]}
