"""Respondent edit-link (magic link) coverage, across the three public
submission types. Submit mints a secret token (returned once); the
hash is stored; the token resolves the submission for pre-fill (GET)
and in-place update (PUT). Wrong tokens 404; the token never leaks into
organiser DTOs; the events edit leaves the encrypted email + dispatch
rows untouched (there's no path from a signup to them).
"""

from __future__ import annotations

from typing import Any

from tests._helpers.events import public_option_ids


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


# --- forms -----------------------------------------------------------


def _create_form(client: Any, headers: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "EL form",
        "locale": "nl",
        "questions": [{"kind": "rating", "prompt": "Score", "required": True}],
    }
    r = client.post("/api/v1/form", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_form_edit_roundtrip(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    ack = client.post(
        f"/api/v1/form/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 3}]},
    ).json()
    token = ack["edit_token"]

    pre = client.get(f"/api/v1/form/by-token/{token}").json()
    assert pre["display_name"] == "Sam"
    assert pre["answers"][qid] == 3

    r = client.put(
        f"/api/v1/form/by-token/{token}",
        json={"display_name": "Sue", "answers": [{"question_id": qid, "answer_int": 5}]},
    )
    assert r.status_code == 200
    assert r.json()["answers"][qid] == 5

    # Edit, not a new submission.
    summary = client.get(f"/api/v1/form/{form['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 1
    after = client.get(f"/api/v1/form/by-token/{token}").json()
    assert after["display_name"] == "Sue"
    assert after["answers"][qid] == 5


def test_form_bad_token_404(client):
    assert client.get("/api/v1/form/by-token/nope").status_code == 404


def test_form_submissions_dto_has_no_token(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    client.post(
        f"/api/v1/form/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_int": 4}]},
    )
    subs = client.get(f"/api/v1/form/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs and "edit_token" not in subs[0] and "edit_token_hash" not in subs[0]


# --- datepolls -------------------------------------------------------


def _create_poll(client: Any, headers: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "EL poll",
        "locale": "nl",
        "slots": [
            {"on_date": "2027-09-01"},
            {"on_date": "2027-09-02", "start_time": "19:00", "end_time": "21:00"},
        ],
    }
    r = client.post("/api/v1/datepoll", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_datepoll_edit_roundtrip(client, organiser_headers):
    poll = _create_poll(client, organiser_headers)
    d0, d1 = poll["slots"][0]["id"], poll["slots"][1]["id"]
    token = client.post(
        f"/api/v1/datepoll/by-slug/{poll['slug']}/submit",
        json={"display_name": "Sam", "note": "first", "answers": [{"datepoll_slot_id": d0, "availability": "yes"}]},
    ).json()["edit_token"]

    pre = client.get(f"/api/v1/datepoll/by-token/{token}").json()
    assert pre["answers"][d0] == "yes"
    assert pre["note"] == "first"

    r = client.put(
        f"/api/v1/datepoll/by-token/{token}",
        json={
            "display_name": "Sam",
            "note": "changed my mind",
            "answers": [
                {"datepoll_slot_id": d0, "availability": "no"},
                {"datepoll_slot_id": d1, "availability": "maybe"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answers"][d0] == "no"
    assert body["answers"][d1] == "maybe"
    assert body["note"] == "changed my mind"

    summary = client.get(f"/api/v1/datepoll/{poll['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 1


def test_datepoll_bad_token_404(client):
    assert client.get("/api/v1/datepoll/by-token/nope").status_code == 404


# --- events ----------------------------------------------------------


def _create_event(client: Any, headers: Any, **overrides: Any) -> dict[str, Any]:
    payload = {
        "name_nl": "EL event",
        "chapter_id": _chapter_id(client, headers),
        "topic_nl": None,
        "location": "Adam",
        "starts_on": "2027-05-01",
        "start_time": "18:00:00",
        "end_time": "20:00:00",
        "source_options": [{"label": "Flyer"}],
        "help_options": [{"label": "opbouwen"}],
        "help_enabled": True,
        "feedback_enabled": True,
        "reminder_enabled": False,
        "locale": "nl",
        **overrides,
    }
    r = client.post("/api/v1/event", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _first_occurrence(client: Any, headers: Any, event: dict[str, Any]) -> dict[str, Any]:
    """The event's first materialised occurrence — its public slug is the
    per-occurrence sign-up target, its id the withdraw/target key."""
    return client.get(f"/api/v1/event/{event['id']}/occurrences", headers=headers).json()["occurrences"][0]


def _occurrence_signups(client: Any, headers: Any, event: dict[str, Any]) -> list[dict[str, Any]]:
    occ = _first_occurrence(client, headers, event)
    return client.get(f"/api/v1/event/{event['id']}/occurrences/{occ['id']}/signups", headers=headers).json()


def _dispatch_count(event_id: str) -> int:
    from backend.database import SessionLocal
    from backend.models import EmailDispatch, Occurrence

    db = SessionLocal()
    try:
        occ_ids = [o.id for o in db.query(Occurrence).filter(Occurrence.event_id == event_id).all()]
        return db.query(EmailDispatch).filter(EmailDispatch.occurrence_id.in_(occ_ids)).count()
    finally:
        db.close()


def test_event_edit_roundtrip(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    picked = public_option_ids(client, occ["slug"], help_labels=("opbouwen",))
    token = client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 2, **picked, "all_upcoming": True},
    ).json()["edit_token"]

    pre = client.get(f"/api/v1/event/by-token/{token}").json()
    assert pre["party_size"] == 2
    assert pre["occurrences"][0]["help_choices"] == picked["help_choices"]
    assert "email" not in pre  # email never reachable from a signup

    r = client.put(
        f"/api/v1/event/by-token/{token}",
        json={"display_name": "Sam", "party_size": 5},
    )
    assert r.status_code == 200
    assert r.json()["party_size"] == 5


def test_event_edit_leaves_email_dispatches_untouched(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    token = client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "email": "sam@local.dev", "all_upcoming": True},
    ).json()["edit_token"]

    before = _dispatch_count(event["id"])
    assert before >= 1  # feedback dispatch created

    client.put(
        f"/api/v1/event/by-token/{token}",
        json={"display_name": "Sam edited", "party_size": 3},
    )
    after = _dispatch_count(event["id"])
    assert after == before  # edit didn't touch the email side at all


def test_event_bad_token_404(client):
    assert client.get("/api/v1/event/by-token/nope").status_code == 404


# --- withdraw (participant deletes their own submission) --------------


def test_form_withdraw(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    token = client.post(
        f"/api/v1/form/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 3}]},
    ).json()["edit_token"]

    assert client.post(f"/api/v1/form/by-token/{token}/withdraw").status_code == 204
    # Submission + its responses are gone; the token no longer resolves.
    assert client.get(f"/api/v1/form/by-token/{token}").status_code == 404
    summary = client.get(f"/api/v1/form/{form['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 0


def test_datepoll_withdraw(client, organiser_headers):
    poll = _create_poll(client, organiser_headers)
    d0 = poll["slots"][0]["id"]
    token = client.post(
        f"/api/v1/datepoll/by-slug/{poll['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"datepoll_slot_id": d0, "availability": "yes"}]},
    ).json()["edit_token"]

    assert client.post(f"/api/v1/datepoll/by-token/{token}/withdraw").status_code == 204
    assert client.get(f"/api/v1/datepoll/by-token/{token}").status_code == 404
    summary = client.get(f"/api/v1/datepoll/{poll['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 0


def test_manage_recurring_booking_calendar(client, organiser_headers):
    """The secret-link manage page can add and remove FUTURE sessions (not
    just cancel), while PAST sessions are frozen: marked ``is_past``, left
    untouched by a session-set update, and un-withdrawable (409)."""
    from datetime import datetime, timedelta

    from backend.database import SessionLocal
    from backend.models import Event as EventModel
    from backend.models import Registration, Signup
    from backend.services import event_recurrence
    from backend.services.events import now_wallclock

    # A recurring event straddling now: weekly ×6 from 16 days ago → three
    # sessions clearly past, three clearly future.
    anchor = now_wallclock() - timedelta(days=16)
    event = _create_event(
        client,
        organiser_headers,
        name="Cursus",
        starts_on=anchor.date().isoformat(),
        start_time="19:00:00",
        end_time="21:00:00",
        period_weeks=1,
        cycle_slots=[anchor.weekday()],
        span_weeks=6,
    )
    # Production skips fabricating past sessions, so back-fill the ones that
    # would exist for a course that has actually been running (as the seed
    # does), to exercise the past-frozen behaviour.
    db = SessionLocal()
    try:
        ev = db.query(EventModel).filter(EventModel.id == event["id"]).one()
        event_recurrence.materialise(db, ev, now_wallclock(), include_past=True)
        db.commit()
    finally:
        db.close()
    now = now_wallclock()
    occs = client.get(f"/api/v1/event/{event['id']}/occurrences", headers=organiser_headers).json()["occurrences"]
    past = [o for o in occs if datetime.fromisoformat(o["starts_at"]) <= now]
    future = [o for o in occs if datetime.fromisoformat(o["starts_at"]) > now]
    assert len(past) >= 2 and len(future) >= 3

    # Public sign-up for the first future session; grab the raw edit token.
    token = client.post(
        f"/api/v1/event/by-slug/{future[0]['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "occurrence_ids": [future[0]["id"]]},
    ).json()["edit_token"]

    # Inject a PAST line item on the same booking (the API can't book a past
    # session, so we seed one directly, as a real attended-then-edited case).
    db = SessionLocal()
    try:
        reg = db.query(Registration).filter(Registration.event_id == event["id"]).one()
        db.add(Signup(registration_id=reg.id, occurrence_id=past[-1]["id"]))
        db.commit()
    finally:
        db.close()

    # GET flags past vs future correctly.
    booking = client.get(f"/api/v1/event/by-token/{token}").json()
    by_id = {o["occurrence_id"]: o for o in booking["occurrences"]}
    assert by_id[past[-1]["id"]]["is_past"] is True
    assert by_id[future[0]["id"]]["is_past"] is False

    # Manage: add a second future session (future[1]) to the selection.
    r = client.put(
        f"/api/v1/event/by-token/{token}/occurrences",
        json={"occurrence_ids": [future[0]["id"], future[1]["id"]], "all_upcoming": False},
    )
    assert r.status_code == 200, r.text
    ids = {o["occurrence_id"] for o in r.json()["occurrences"]}
    assert future[0]["id"] in ids and future[1]["id"] in ids  # added
    assert past[-1]["id"] in ids  # past untouched

    # Deselect every future session: only the frozen past one remains.
    r = client.put(
        f"/api/v1/event/by-token/{token}/occurrences",
        json={"occurrence_ids": [], "all_upcoming": False},
    )
    assert {o["occurrence_id"] for o in r.json()["occurrences"]} == {past[-1]["id"]}

    # A past session can't be withdrawn after it happened.
    assert client.post(f"/api/v1/event/by-token/{token}/occurrences/{past[-1]['id']}/withdraw").status_code == 409


def test_event_withdraw_deletes_signup(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    token = client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 2, "help_choices": [], "all_upcoming": True},
    ).json()["edit_token"]

    assert client.post(f"/api/v1/event/by-token/{token}/withdraw").status_code == 204
    assert client.get(f"/api/v1/event/by-token/{token}").status_code == 404


def test_event_withdraw_leaves_email_dispatches_intact(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    token = client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "email": "sam@local.dev", "all_upcoming": True},
    ).json()["edit_token"]

    before = _dispatch_count(event["id"])
    assert before >= 1  # feedback dispatch created at signup

    assert client.post(f"/api/v1/event/by-token/{token}/withdraw").status_code == 204

    # Withdrawing the signup leaves the decoupled dispatch rows alone, by
    # design (no signup_id link) — the person may still get the email.
    after = _dispatch_count(event["id"])
    assert after == before


def test_withdraw_bad_token_404(client):
    assert client.post("/api/v1/form/by-token/nope/withdraw").status_code == 404
    assert client.post("/api/v1/datepoll/by-token/nope/withdraw").status_code == 404
    assert client.post("/api/v1/event/by-token/nope/withdraw").status_code == 404


# --- organiser recovery (shared across all four entities) -------------
#
# Only the token hash is stored, so recovery ROTATES the link: the old
# token dies, the fresh one is returned exactly once, and the row's
# ``link_recovered_at`` is stamped permanently — the public edit page
# discloses that an organiser has held the link.


def _recover(client: Any, headers: Any, path: str) -> str:
    r = client.post(path, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["edit_token"]


def test_event_recovery_rotates_and_stamps(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    old = client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 2, "help_choices": [], "all_upcoming": True},
    ).json()["edit_token"]
    rows = _occurrence_signups(client, organiser_headers, event)
    assert rows[0]["link_recovered_at"] is None
    rid = rows[0]["registration_id"]
    fresh = _recover(client, organiser_headers, f"/api/v1/event/{event['id']}/registrations/{rid}/edit-link")

    assert client.get(f"/api/v1/event/by-token/{old}").status_code == 404  # old link dead
    page = client.get(f"/api/v1/event/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None
    rows = _occurrence_signups(client, organiser_headers, event)
    assert rows[0]["link_recovered_at"] is not None


def test_event_recovery_stamp_survives_edits_and_updates_on_recopy(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "help_choices": [], "all_upcoming": True},
    )
    rid = _occurrence_signups(client, organiser_headers, event)[0]["registration_id"]
    path = f"/api/v1/event/{event['id']}/registrations/{rid}/edit-link"
    token = _recover(client, organiser_headers, path)
    first = client.get(f"/api/v1/event/by-token/{token}").json()["link_recovered_at"]

    # The participant editing their signup never clears the stamp.
    r = client.put(
        f"/api/v1/event/by-token/{token}",
        json={"display_name": "Sam", "party_size": 3},
    )
    assert r.status_code == 200 and r.json()["link_recovered_at"] == first

    # A second recovery moves the stamp forward (banner shows the latest).
    token2 = _recover(client, organiser_headers, path)
    second = client.get(f"/api/v1/event/by-token/{token2}").json()["link_recovered_at"]
    assert second >= first


def test_event_recovery_requires_auth_and_scope(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event)
    client.post(
        f"/api/v1/event/by-slug/{occ['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "help_choices": [], "all_upcoming": True},
    )
    rid = _occurrence_signups(client, organiser_headers, event)[0]["registration_id"]
    assert client.post(f"/api/v1/event/{event['id']}/registrations/{rid}/edit-link").status_code == 401
    r = client.post(f"/api/v1/event/{event['id']}/registrations/does-not-exist/edit-link", headers=organiser_headers)
    assert r.status_code == 404


def test_form_recovery_rotates_and_stamps(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    old = client.post(
        f"/api/v1/form/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 3}]},
    ).json()["edit_token"]
    subs = client.get(f"/api/v1/form/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["link_recovered_at"] is None
    fresh = _recover(
        client, organiser_headers, f"/api/v1/form/{form['id']}/submissions/{subs[0]['submission_id']}/edit-link"
    )

    assert client.get(f"/api/v1/form/by-token/{old}").status_code == 404
    page = client.get(f"/api/v1/form/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None
    subs = client.get(f"/api/v1/form/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["link_recovered_at"] is not None


def test_datepoll_recovery_rotates_and_stamps(client, organiser_headers):
    poll = _create_poll(client, organiser_headers)
    d0 = poll["slots"][0]["id"]
    old = client.post(
        f"/api/v1/datepoll/by-slug/{poll['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"datepoll_slot_id": d0, "availability": "yes"}]},
    ).json()["edit_token"]
    subs = client.get(f"/api/v1/datepoll/{poll['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["link_recovered_at"] is None
    fresh = _recover(
        client, organiser_headers, f"/api/v1/datepoll/{poll['id']}/submissions/{subs[0]['submission_id']}/edit-link"
    )

    assert client.get(f"/api/v1/datepoll/by-token/{old}").status_code == 404
    page = client.get(f"/api/v1/datepoll/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None


def test_chore_recovery_rotates_and_stamps(client, organiser_headers):
    body = {
        "chapter_id": _chapter_id(client, organiser_headers),
        "name_nl": "EL roster",
        "starts_on": "2027-01-04",
        "chores": [{"name": "Bins", "cycle_slots": [2]}],
    }
    roster = client.post("/api/v1/chore", headers=organiser_headers, json=body).json()
    old = client.post(
        f"/api/v1/chore/by-slug/{roster['slug']}/enroll",
        json={"display_name": "Sam", "chore_ids": [roster["chores"][0]["id"]]},
    ).json()["edit_token"]
    vols = client.get(f"/api/v1/chore/{roster['id']}/volunteers", headers=organiser_headers).json()
    assert vols[0]["link_recovered_at"] is None
    fresh = _recover(client, organiser_headers, f"/api/v1/chore/{roster['id']}/volunteers/{vols[0]['id']}/edit-link")

    assert client.get(f"/api/v1/chore/by-token/{old}").status_code == 404
    page = client.get(f"/api/v1/chore/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None
    vols = client.get(f"/api/v1/chore/{roster['id']}/volunteers", headers=organiser_headers).json()
    assert vols[0]["link_recovered_at"] is not None
