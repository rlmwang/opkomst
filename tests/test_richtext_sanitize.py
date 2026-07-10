"""The rich-text sanitizer is the single chokepoint that keeps
organiser-authored bodies from becoming executable markup on public
pages (they are rendered with ``v-html`` downstream). These tests pin
that guarantee: the XSS matrix, idempotency, the plaintext inverse, the
visible-length gate, and that every entity body field actually runs
through the sanitizer while the per-chore label stays plain.
"""

from datetime import date, time

import pytest
from pydantic import ValidationError

from backend.schemas.chores import ChoreIn, RosterCreate
from backend.schemas.datepolls import DatepollCreate
from backend.schemas.events import EventCreate
from backend.schemas.forms import FormCreate
from backend.services.sanitize import (
    VISIBLE_MAX_LENGTH,
    html_to_text,
    sanitize_richtext,
)

# --- The XSS matrix -------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        '<a href="javascript:alert(1)">x</a>',
        '<a href="data:text/html,<script>alert(1)</script>">x</a>',
        '<b onclick="steal()">c</b>',
        "<style>body{background:url(evil)}</style>text",
        "<svg><script>alert(1)</script></svg>",
        "<iframe src=evil></iframe>",
        '<a href="vbscript:msgbox(1)">x</a>',
    ],
)
def test_no_script_or_handlers_survive(payload: str) -> None:
    out = sanitize_richtext(payload) or ""
    lowered = out.lower()
    assert "<script" not in lowered
    assert "<iframe" not in lowered
    assert "<style" not in lowered
    assert "onerror" not in lowered
    assert "onclick" not in lowered
    assert "javascript:" not in lowered
    assert "vbscript:" not in lowered
    assert "data:text/html" not in lowered


def test_marks_survive_intact() -> None:
    out = sanitize_richtext("<strong>b</strong><em>i</em><u>u</u><s>s</s><p>para</p>")
    assert out == "<strong>b</strong><em>i</em><u>u</u><s>s</s><p>para</p>"


def test_safe_link_keeps_href_and_gets_forced_rel() -> None:
    out = sanitize_richtext('<a href="https://opkomst.nu">x</a>') or ""
    assert 'href="https://opkomst.nu"' in out
    assert 'rel="nofollow noopener noreferrer"' in out


def test_mailto_link_allowed() -> None:
    out = sanitize_richtext('<a href="mailto:a@b.nl">m</a>') or ""
    assert 'href="mailto:a@b.nl"' in out


def test_dangerous_link_loses_href_but_keeps_text() -> None:
    out = sanitize_richtext('<a href="javascript:alert(1)">click</a>') or ""
    assert "href" not in out
    assert "click" in out


def test_empty_and_whitespace_collapse_to_none() -> None:
    assert sanitize_richtext(None) is None
    assert sanitize_richtext("   ") is None
    assert sanitize_richtext("<p>  </p>") is None


def test_idempotent() -> None:
    once = sanitize_richtext("<strong>x</strong><script>bad()</script>")
    twice = sanitize_richtext(once)
    assert once == twice


# --- Plaintext inverse (OG / ICS / email) ---------------------------------


def test_html_to_text_strips_tags() -> None:
    assert html_to_text("<strong>Voku</strong> &amp; docu") == "Voku & docu"
    assert html_to_text("<p>one</p><p>two</p>") == "one\n\ntwo"
    assert html_to_text("a<br>b") == "a\nb"
    assert html_to_text(None) == ""


# --- The chokepoint: every body field sanitizes ---------------------------


def _event(topic: str) -> EventCreate:
    return EventCreate(
        name_nl="x",
        chapter_id="c",
        topic_nl=topic,
        location="loc",
        starts_on=date(2026, 7, 1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        source_options=["w"],
        image_artist_instagram=None,
    )


def test_event_topic_is_sanitized() -> None:
    assert "<script" not in (_event("<script>x</script>hi").topic_nl or "")


def test_form_description_is_sanitized() -> None:
    f = FormCreate(
        name_nl="f",
        chapter_id="c",
        description_nl="<script>x</script>ok",
        image_artist_instagram=None,
    )
    assert f.description_nl == "ok"


def test_datepoll_description_is_sanitized() -> None:
    d = DatepollCreate(
        name_nl="d",
        chapter_id="c",
        description_nl="<img src=x onerror=y>ok",
        image_artist_instagram=None,
    )
    assert (d.description_nl or "") == "ok"


def test_roster_description_is_sanitized() -> None:
    r = RosterCreate(
        chapter_id="c",
        name_nl="r",
        description_nl="<b onclick=x>ok</b>",
        image_artist_instagram=None,
        period_weeks=1,
        starts_on=date(2026, 7, 1),
    )
    # <b> is not allowlisted, so the tag drops but the text stays.
    assert (r.description_nl or "") == "ok"


def test_per_chore_description_stays_plain() -> None:
    # The short per-chore label is escaped-rendered, not v-html'd, so it
    # is deliberately left un-sanitized (literal text preserved).
    c = ChoreIn(name="dishes", description="<b>literal</b>")
    assert c.description == "<b>literal</b>"


# --- Visible-length gate --------------------------------------------------


def test_visible_length_over_cap_rejected() -> None:
    with pytest.raises(ValidationError):
        _event("<strong>" + ("a" * (VISIBLE_MAX_LENGTH + 1)) + "</strong>")


def test_markup_does_not_count_against_visible_cap() -> None:
    # Lots of markup, few visible chars: must pass.
    body = "".join(f"<strong>{c}</strong>" for c in "a" * 100)
    assert _event(body).topic_nl is not None
