"""Audit: every read endpoint stays inside a query budget.

Builds one of each entity through the real API, then walks every
``GET`` path in ``openapi.json``, calls it, and counts the SQL
statements the request issued. A path over its budget fails here.

Why a test and not a profiling session: the two round trips every
authenticated request used to spend on an eagerly-loaded ``chapters``
collection were invisible for the whole life of the codebase, because
nothing ever asserted how many queries a page costs. An N+1 does not
break a feature, so no functional test notices it; it just makes every
page slower until somebody goes looking.

``BUDGETS`` is the ratchet. A GET path with no entry fails the test, so
a new endpoint has to declare what it costs, and a number that turns out
to be too generous can be tightened here and will then stay tight. The
numbers are ceilings with a little headroom, not measurements: raise one
only when the extra query is buying something, and say what in the
commit message.

The counts are per request against a small fixture dataset, so they
measure *shape* rather than volume. That is the point. A budget that
holds at three rows and breaks at three hundred is exactly the N+1 this
test exists to catch.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event as sa_event

# Ceiling on SQL statements per GET request, by ``openapi.json`` path.
#
# One query of the ceiling is the authenticated user; endpoints that
# scope by chapter spend a second on the membership set. The rest is the
# endpoint's own work, and should be one query per fact it reports.
#
# Options are rows rather than JSON columns
# (``docs/design-question-edits.md``), so a read that shows them spends
# a query on them: one for a form's choices, two for an event's source
# and help lists. Per page, never per question or per option.
BUDGETS: dict[str, int] = {
    # -- infrastructure ------------------------------------------------
    "/health": 0,
    "/health/full": 1,
    # -- auth / admin / settings ---------------------------------------
    "/api/v1/auth/me": 2,
    "/api/v1/admin/users": 3,
    "/api/v1/admin/users/pending-count": 2,
    "/api/v1/settings": 1,
    "/api/v1/chapters": 2,
    "/api/v1/chapters/{chapter_id}/usage": 10,
    "/api/v1/tenants/{tenant_slug}/chapters": 2,
    "/api/v1/tenants/{tenant_slug}/agenda/{slug}": 3,
    # -- events --------------------------------------------------------
    "/api/v1/event": 3,
    "/api/v1/event/archived": 3,
    "/api/v1/event/{event_id}": 8,
    "/api/v1/event/{event_id}/occurrences": 6,
    "/api/v1/event/{event_id}/occurrences/{occurrence_id}/signups": 6,
    "/api/v1/event/{event_id}/occurrences/{occurrence_id}/stats": 7,
    "/api/v1/event/{event_id}/feedback-summary": 9,
    "/api/v1/event/{event_id}/feedback-submissions": 4,
    "/api/v1/event/by-slug/{slug}": 4,
    "/api/v1/event/by-slug/{slug}/qr.svg": 2,
    "/api/v1/event/by-slug/{slug}/event.ics": 2,
    "/api/v1/event/by-slug/{slug}/feedback-preview": 2,
    "/api/v1/event/by-slug/{slug}/email-preview/{channel}": 2,
    "/api/v1/event/by-token/{token}": 4,
    # -- feedback ------------------------------------------------------
    "/api/v1/feedback/questions": 1,
    "/api/v1/feedback/{token}": 4,
    # -- forms / quizzes / kompassen (one factory, three mounts) -------
    "/api/v1/form": 3,
    "/api/v1/form/archived": 3,
    "/api/v1/form/{form_id}": 5,
    "/api/v1/form/{form_id}/summary": 6,
    "/api/v1/form/{form_id}/submissions": 5,
    "/api/v1/form/by-slug/{slug}": 3,
    "/api/v1/form/by-slug/{slug}/qr.svg": 2,
    "/api/v1/form/by-token/{token}": 5,
    "/api/v1/quiz": 3,
    "/api/v1/quiz/archived": 3,
    "/api/v1/quiz/{form_id}": 5,
    "/api/v1/quiz/{form_id}/summary": 7,
    "/api/v1/quiz/{form_id}/submissions": 5,
    "/api/v1/quiz/by-slug/{slug}": 3,
    "/api/v1/quiz/by-slug/{slug}/qr.svg": 2,
    "/api/v1/quiz/by-token/{token}": 5,
    "/api/v1/compass": 3,
    "/api/v1/compass/archived": 3,
    "/api/v1/compass/{form_id}": 6,
    "/api/v1/compass/{form_id}/summary": 8,
    "/api/v1/compass/{form_id}/submissions": 5,
    "/api/v1/compass/by-slug/{slug}": 4,
    "/api/v1/compass/by-slug/{slug}/qr.svg": 2,
    "/api/v1/compass/by-token/{token}": 5,
    # -- datepolls -----------------------------------------------------
    "/api/v1/datepoll": 3,
    "/api/v1/datepoll/archived": 3,
    "/api/v1/datepoll/{datepoll_id}": 6,
    "/api/v1/datepoll/{datepoll_id}/summary": 6,
    "/api/v1/datepoll/{datepoll_id}/submissions": 4,
    "/api/v1/datepoll/by-slug/{slug}": 3,
    "/api/v1/datepoll/by-slug/{slug}/qr.svg": 2,
    "/api/v1/datepoll/by-token/{token}": 5,
    # -- chore rosters -------------------------------------------------
    "/api/v1/chore": 3,
    "/api/v1/chore/archived": 3,
    "/api/v1/chore/{roster_id}": 6,
    "/api/v1/chore/{roster_id}/schedule": 6,
    "/api/v1/chore/{roster_id}/volunteers": 4,
    "/api/v1/chore/{roster_id}/accountability": 7,
    "/api/v1/chore/{roster_id}/calendar": 6,
    "/api/v1/chore/{roster_id}/rebalance/preview": 9,
    "/api/v1/chore/by-slug/{slug}": 3,
    "/api/v1/chore/by-slug/{slug}/qr.svg": 2,
    "/api/v1/chore/by-token/{token}": 6,
    "/api/v1/chore/by-token/{token}/calendar": 6,
    # -- whatsapp (organisation-only tool) -----------------------------
    "/api/v1/whatsapp/qr": 3,
    "/api/v1/whatsapp/status": 3,
}

# Paths this audit cannot reach, and why. Declared rather than silently
# skipped: without the list, a new endpoint that the fixtures happen not
# to reach would look covered while nothing measured it.
UNMEASURED: dict[str, str] = {
    "/api/v1/event/by-token/{token}": "needs an emailed edit token",
    "/api/v1/form/by-token/{token}": "needs an emailed edit token",
    "/api/v1/quiz/by-token/{token}": "needs an emailed edit token",
    "/api/v1/compass/by-token/{token}": "needs an emailed edit token",
    "/api/v1/datepoll/by-token/{token}": "needs an emailed edit token",
    "/api/v1/chore/by-token/{token}": "needs a volunteer's personal link",
    "/api/v1/chore/by-token/{token}/calendar": "needs a volunteer's personal link",
    "/api/v1/feedback/{token}": "needs a feedback token, minted by the mail worker",
    "/api/v1/chapters/{chapter_id}/usage": "admin-only surface, 403 for the audit's organiser",
    "/api/v1/chore/{roster_id}/rebalance/preview": "409 until the roster is activated",
    "/api/v1/whatsapp/qr": "403 without the WhatsApp tool configured",
    "/api/v1/whatsapp/status": "403 without the WhatsApp tool configured",
}


# Transaction control, not work the endpoint asked for. The test
# database runs each test inside a transaction and gives every session
# a savepoint (``conftest.db``), so a request under test emits a
# SAVEPOINT / ROLLBACK pair that it would never emit in production.
_TRANSACTION_CONTROL = re.compile(r"^(SAVEPOINT|RELEASE|ROLLBACK|BEGIN|COMMIT)\b", re.IGNORECASE)


@contextmanager
def count_queries() -> Iterator[list[str]]:
    """Collect every SQL statement executed inside the block, except the
    transaction control the test harness adds.

    Listens on the ``Engine`` class rather than one engine instance, so
    it sees the session the request handler makes for itself rather than
    only the test's own."""
    from sqlalchemy.engine import Engine

    seen: list[str] = []

    def _after(_conn, _cursor, statement, _params, _context, _many):  # type: ignore[no-untyped-def]
        normalised = " ".join(statement.split())
        if not _TRANSACTION_CONTROL.match(normalised):
            seen.append(normalised)

    sa_event.listen(Engine, "after_cursor_execute", _after)
    try:
        yield seen
    finally:
        sa_event.remove(Engine, "after_cursor_execute", _after)


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _build_fixtures(client: Any, headers: Any) -> dict[str, str]:
    """One of each entity, made the way the app makes them, plus enough
    answers that the summary endpoints have something to aggregate.

    Created over HTTP rather than by inserting rows: a budget is only
    meaningful against data shaped the way production data is."""
    chapter = _chapter_id(client, headers)
    ids: dict[str, str] = {"chapter_id": chapter, "tenant_slug": "rsp"}

    event = client.post(
        "/api/v1/event",
        headers=headers,
        json={
            "name_nl": "Budget event",
            "chapter_id": chapter,
            "topic_nl": None,
            "location": "Amsterdam",
            "starts_on": "2027-05-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "Flyer"}],
            "help_options": [{"label": "opbouwen"}],
            "help_enabled": True,
            "feedback_enabled": True,
            # Both channels on, so the two email-preview routes render
            # instead of 404-ing and escaping the audit.
            "reminder_enabled": True,
            "locale": "nl",
        },
    ).json()
    ids["event_id"] = event["id"]
    panel = client.get(f"/api/v1/event/{event['id']}/occurrences", headers=headers).json()
    occurrences = panel["occurrences"]
    assert occurrences, "event fixture materialised no occurrence to measure against"
    ids["occurrence_id"] = occurrences[0]["id"]
    ids["event_slug"] = occurrences[0]["slug"]
    # Two sign-ups, so the headcount aggregates read more than one row.
    for name in ("Ada", "Bo"):
        client.post(
            f"/api/v1/signups/{occurrences[0]['slug']}",
            json={"name": name, "party_size": 2, "source": "Flyer", "help_choices": []},
        )

    for product, extra in (
        ("form", {}),
        ("quiz", {}),
        ("compass", {}),
    ):
        body: dict[str, Any] = {
            "chapter_id": chapter,
            "name_nl": f"Budget {product}",
            "locale": "nl",
            "questions": [{"kind": "short_text", "prompt": "Waarom?", "required": False}],
            **extra,
        }
        if product == "quiz":
            body["questions"] = [
                {
                    "kind": "single_choice",
                    "prompt": "Welke?",
                    "required": True,
                    "options": [{"label": "A", "is_correct": True}, {"label": "B"}],
                    "points": 1,
                }
            ]
        if product == "compass":
            body["axes"] = [
                {"axis": "x", "name": "Economie", "low_name": "Links", "high_name": "Rechts"},
                {"axis": "y", "name": "Cultuur", "low_name": "Open", "high_name": "Behoud"},
            ]
            body["questions"] = [
                {"kind": "rating", "prompt": "Hoezo?", "required": True, "pole": "x_high"},
                {"kind": "rating", "prompt": "En dit?", "required": True, "pole": "y_low"},
            ]
        created = client.post(f"/api/v1/{product}", headers=headers, json=body)
        assert created.status_code == 201, created.text
        ids[f"{product}_id"] = created.json()["id"]
        ids[f"{product}_slug"] = created.json()["slug"]

    poll = client.post(
        "/api/v1/datepoll",
        headers=headers,
        json={
            "chapter_id": chapter,
            "name_nl": "Budget poll",
            "locale": "nl",
            "slots": [{"on_date": "2027-06-01"}, {"on_date": "2027-06-02"}],
        },
    ).json()
    ids["datepoll_id"] = poll["id"]
    ids["datepoll_slug"] = poll["slug"]

    roster = client.post(
        "/api/v1/chore",
        headers=headers,
        json={
            "chapter_id": chapter,
            "name_nl": "Budget roster",
            "starts_on": "2027-01-04",
            "chores": [{"name": "Bins", "cycle_slots": [2]}],
        },
    ).json()
    ids["roster_id"] = roster["id"]
    ids["roster_slug"] = roster["slug"]
    return ids


# Which entity's slug each mount's ``by-slug`` routes want.
_SLUG_BY_PREFIX = {
    "/api/v1/event": "event_slug",
    "/api/v1/form": "form_slug",
    "/api/v1/quiz": "quiz_slug",
    "/api/v1/compass": "compass_slug",
    "/api/v1/datepoll": "datepoll_slug",
    "/api/v1/chore": "roster_slug",
    "/api/v1/tenants": "chapter_slug",
}
# Which entity id each mount's ``{form_id}`` means.
_FORM_ID_BY_PREFIX = {
    "/api/v1/form": "form_id",
    "/api/v1/quiz": "quiz_id",
    "/api/v1/compass": "compass_id",
}


def _fill(path: str, ids: dict[str, str]) -> str | None:
    """A callable URL for one openapi path, or None when it needs
    something this audit does not mint (an emailed edit token)."""
    if "{token}" in path:
        return None
    url = path
    prefix = "/".join(path.split("/")[:4])
    if "{form_id}" in url:
        key = _FORM_ID_BY_PREFIX.get(prefix)
        if key is None:
            return None
        url = url.replace("{form_id}", ids[key])
    if "{slug}" in url:
        key = _SLUG_BY_PREFIX.get(prefix)
        if key is None or key not in ids:
            return None
        url = url.replace("{slug}", ids[key])
    for name, value in ids.items():
        url = url.replace("{" + name + "}", value)
    url = url.replace("{channel}", "reminder")
    return None if re.search(r"\{[a-z_]+\}", url) else url


def test_every_get_path_declares_a_budget() -> None:
    """A new read endpoint has to say what it costs. Without this the
    budgets only cover what existed when they were written."""
    spec = json.loads((pathlib.Path(__file__).resolve().parents[1] / "openapi.json").read_text())
    paths = {p for p, ops in spec["paths"].items() if "get" in ops}
    undeclared = sorted(paths - set(BUDGETS))
    assert not undeclared, (
        "GET endpoints with no query budget: "
        + ", ".join(undeclared)
        + ". Add each to BUDGETS in tests/test_query_budget.py with the number of "
        "queries it issues, so an N+1 introduced later fails here."
    )
    stale = sorted(set(BUDGETS) - paths)
    assert not stale, f"BUDGETS names paths that no longer exist: {', '.join(stale)}"


def test_read_endpoints_stay_within_their_query_budget(client, organiser_headers, admin_headers) -> None:
    spec = json.loads((pathlib.Path(__file__).resolve().parents[1] / "openapi.json").read_text())
    ids = _build_fixtures(client, organiser_headers)
    # The agenda route is per chapter and wants the chapter's own slug.
    ids["chapter_slug"] = client.get("/api/v1/chapters", headers=organiser_headers).json()[0]["slug"]

    over: list[str] = []
    skipped: set[str] = set()
    for path in sorted(p for p, ops in spec["paths"].items() if "get" in ops):
        url = _fill(path, ids)
        if url is None:
            skipped.add(path)
            continue
        headers = admin_headers if "/admin/" in path or path.endswith("/settings") else organiser_headers
        client.get(url, headers=headers)  # warm: first call compiles statements
        with count_queries() as seen:
            response = client.get(url, headers=headers)
        if response.status_code >= 400:
            # A 4xx short-circuits before the endpoint does its work, so
            # its count would measure the guard rather than the page.
            skipped.add(path)
            continue
        budget = BUDGETS[path]
        if len(seen) > budget:
            repeated = sorted({s for s in seen if seen.count(s) > 1})
            detail = f"\n      repeats: {repeated[0][:90]}" if repeated else ""
            over.append(f"  {path}: {len(seen)} queries, budget {budget}{detail}")

    assert not over, (
        "Endpoints over their query budget:\n"
        + "\n".join(over)
        + "\n\nEither the change added a round trip that isn't buying anything, "
        "or the budget in tests/test_query_budget.py needs raising on purpose."
    )
    # The skip list is declared, so a path that quietly stops being
    # reachable cannot pass as measured.
    assert skipped == set(UNMEASURED), (
        f"unreachable paths changed.\n  now unmeasured: {sorted(skipped - set(UNMEASURED))}"
        f"\n  now measurable (drop from UNMEASURED): {sorted(set(UNMEASURED) - skipped)}"
    )


def test_user_list_does_not_query_per_user(client, admin_headers, db) -> None:
    """``/admin/users`` renders each user's chapter memberships, and
    ``User.chapters`` is lazily loaded because ~50 other endpoints load
    a user and never touch it. This is the one page that does, so it has
    to eager-load them for the whole list; without that it spends a
    query per row."""
    from backend.models import User

    client.get("/api/v1/admin/users", headers=admin_headers)
    with count_queries() as before:
        client.get("/api/v1/admin/users", headers=admin_headers)
    for i in range(5):
        db.add(User(email=f"budget{i}@local.dev", name=f"B{i}", role="organiser", is_approved=True))
    db.commit()
    with count_queries() as after:
        client.get("/api/v1/admin/users", headers=admin_headers)

    assert len(after) == len(before), (
        f"/api/v1/admin/users issued {len(before)} queries for 2 users and {len(after)} for 7: "
        "it is loading each user's chapters one row at a time."
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "/api/v1/event",
            {
                "name_nl": "Row count",
                "topic_nl": None,
                "location": "Rotterdam",
                "starts_on": "2027-08-01",
                "start_time": "18:00:00",
                "end_time": "20:00:00",
                "source_options": [{"label": "Flyer"}],
                "help_options": [],
                "help_enabled": False,
                "feedback_enabled": False,
                "reminder_enabled": False,
                "locale": "nl",
                # Weekly for six weeks, so the event materialises several
                # occurrences. With one occurrence a bad join to them
                # duplicates nothing and this test proves nothing.
                "period_weeks": 1,
                "cycle_slots": [0, 3],
                "span_weeks": 6,
            },
        ),
        (
            "/api/v1/form",
            {
                "name_nl": "Row count",
                "locale": "nl",
                "questions": [{"kind": "short_text", "prompt": "?", "required": False}],
            },
        ),
        (
            "/api/v1/chore",
            {
                "name_nl": "Row count",
                "starts_on": "2027-03-01",
                "chores": [{"name": "Mop", "cycle_slots": [1]}, {"name": "Bins", "cycle_slots": [3]}],
            },
        ),
        (
            "/api/v1/datepoll",
            {"name_nl": "Row count", "locale": "nl", "slots": [{"on_date": "2027-09-01"}, {"on_date": "2027-09-02"}]},
        ),
    ],
)
def test_list_returns_one_row_per_entity(client, organiser_headers, path: str, body: dict) -> None:
    """One entity, one card.

    These lists are built by a single statement that also fetches each
    row's counts and related names. Those are scalar subqueries and
    ``LATERAL ... LIMIT 1`` precisely so the result stays one row per
    entity. Rewriting any of them as a plain join to a child table
    (registrations, occurrences, submissions, chores, volunteers, slots)
    returns a row per combination instead, which shows up as repeated
    cards and as counts that are silently multiplied.

    A query budget cannot catch that: it is still one query. The row
    count is what catches it, so it is asserted here.
    """
    ids = _build_fixtures(client, organiser_headers)
    body = {**body, "chapter_id": ids["chapter_id"]}

    before = len(client.get(path, headers=organiser_headers).json())
    created = client.post(path, headers=organiser_headers, json=body)
    assert created.status_code == 201, created.text
    after = client.get(path, headers=organiser_headers).json()

    assert len(after) == before + 1, (
        f"{path} returned {len(after)} rows after adding one entity to {before}. "
        "A child table is joined directly instead of aggregated, so entities repeat."
    )
    assert len({row["id"] for row in after}) == len(after), f"{path} returned the same entity more than once"


@pytest.mark.parametrize("path", ["/api/v1/event", "/api/v1/form", "/api/v1/chore"])
def test_list_endpoints_do_not_scale_queries_with_row_count(client, organiser_headers, path: str) -> None:
    """The N+1 guard proper: the same endpoint, with more rows behind
    it, issues the same number of queries.

    A budget alone cannot catch this — one extra row is one extra query
    and still under the ceiling. Doubling the data and demanding an
    unchanged count is what makes a per-row query fail."""
    ids = _build_fixtures(client, organiser_headers)
    chapter = ids["chapter_id"]

    client.get(path, headers=organiser_headers)
    with count_queries() as before:
        client.get(path, headers=organiser_headers)

    bodies: dict[str, dict[str, Any]] = {
        "/api/v1/event": {
            "name_nl": "Second",
            "chapter_id": chapter,
            "topic_nl": None,
            "location": "Rotterdam",
            "starts_on": "2027-07-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "Flyer"}],
            "help_options": [],
            "help_enabled": False,
            "feedback_enabled": False,
            "reminder_enabled": False,
            "locale": "nl",
        },
        "/api/v1/form": {
            "chapter_id": chapter,
            "name_nl": "Second",
            "locale": "nl",
            "questions": [{"kind": "short_text", "prompt": "Nog iets?", "required": False}],
        },
        "/api/v1/chore": {
            "chapter_id": chapter,
            "name_nl": "Second",
            "starts_on": "2027-02-01",
            "chores": [{"name": "Mop", "cycle_slots": [1]}],
        },
    }
    for _ in range(3):
        created = client.post(path, headers=organiser_headers, json=bodies[path])
        assert created.status_code == 201, created.text

    with count_queries() as after:
        client.get(path, headers=organiser_headers)

    assert len(after) == len(before), (
        f"{path} issued {len(before)} queries for 1 row and {len(after)} for 4: "
        "the endpoint queries per row instead of per page."
    )
