"""Respondent edit-link (magic link) coverage, across the three public
submission types. Submit mints a secret token (returned once); the
hash is stored; the token resolves the submission for pre-fill (GET)
and in-place update (PUT). Wrong tokens 404; the token never leaks into
organiser DTOs; the events edit leaves the encrypted email + dispatch
rows untouched (there's no path from a signup to them).
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


# --- forms -----------------------------------------------------------


def _create_form(client: Any, headers: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name": "EL form",
        "locale": "nl",
        "questions": [{"kind": "rating", "prompt": "Score", "required": True}],
    }
    r = client.post("/api/v1/forms", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_form_edit_roundtrip(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    ack = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 3}]},
    ).json()
    token = ack["edit_token"]

    pre = client.get(f"/api/v1/forms/by-token/{token}").json()
    assert pre["display_name"] == "Sam"
    assert pre["answers"][qid] == 3

    r = client.put(
        f"/api/v1/forms/by-token/{token}",
        json={"display_name": "Sue", "answers": [{"question_id": qid, "answer_int": 5}]},
    )
    assert r.status_code == 200
    assert r.json()["answers"][qid] == 5

    # Edit, not a new submission.
    summary = client.get(f"/api/v1/forms/{form['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 1
    after = client.get(f"/api/v1/forms/by-token/{token}").json()
    assert after["display_name"] == "Sue"
    assert after["answers"][qid] == 5


def test_form_bad_token_404(client):
    assert client.get("/api/v1/forms/by-token/nope").status_code == 404


def test_form_submissions_dto_has_no_token(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_int": 4}]},
    )
    subs = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs and "edit_token" not in subs[0] and "edit_token_hash" not in subs[0]


# --- datepolls -------------------------------------------------------


def _create_poll(client: Any, headers: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name": "EL poll",
        "locale": "nl",
        "slots": [
            {"on_date": "2027-09-01"},
            {"on_date": "2027-09-02", "start_time": "19:00", "end_time": "21:00"},
        ],
    }
    r = client.post("/api/v1/datepolls", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_datepoll_edit_roundtrip(client, organiser_headers):
    poll = _create_poll(client, organiser_headers)
    d0, d1 = poll["slots"][0]["id"], poll["slots"][1]["id"]
    token = client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={"display_name": "Sam", "note": "first", "answers": [{"datepoll_slot_id": d0, "availability": "yes"}]},
    ).json()["edit_token"]

    pre = client.get(f"/api/v1/datepolls/by-token/{token}").json()
    assert pre["answers"][d0] == "yes"
    assert pre["note"] == "first"

    r = client.put(
        f"/api/v1/datepolls/by-token/{token}",
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

    summary = client.get(f"/api/v1/datepolls/{poll['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 1


def test_datepoll_bad_token_404(client):
    assert client.get("/api/v1/datepolls/by-token/nope").status_code == 404


# --- events ----------------------------------------------------------


def _create_event(client: Any, headers: Any, **overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "EL event",
        "chapter_id": _chapter_id(client, headers),
        "topic": None,
        "location": "Adam",
        "starts_at": "2027-05-01T18:00:00",
        "ends_at": "2027-05-01T20:00:00",
        "source_options": ["Flyer"],
        "help_options": ["opbouwen"],
        "feedback_enabled": True,
        "reminder_enabled": False,
        "locale": "nl",
        **overrides,
    }
    r = client.post("/api/v1/events", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_event_edit_roundtrip(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    token = client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 2, "help_choices": ["opbouwen"]},
    ).json()["edit_token"]

    pre = client.get(f"/api/v1/events/by-token/{token}").json()
    assert pre["party_size"] == 2 and pre["help_choices"] == ["opbouwen"]
    assert "email" not in pre  # email never reachable from a signup

    r = client.put(
        f"/api/v1/events/by-token/{token}",
        json={"display_name": "Sam", "party_size": 5, "help_choices": []},
    )
    assert r.status_code == 200
    assert r.json()["party_size"] == 5


def test_event_edit_leaves_email_dispatches_untouched(client, organiser_headers):
    from backend.database import SessionLocal
    from backend.models import EmailDispatch

    event = _create_event(client, organiser_headers)
    token = client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "email": "sam@local.dev"},
    ).json()["edit_token"]

    db = SessionLocal()
    try:
        before = db.query(EmailDispatch).filter(EmailDispatch.event_id == event["id"]).count()
    finally:
        db.close()
    assert before >= 1  # feedback dispatch created

    client.put(
        f"/api/v1/events/by-token/{token}",
        json={"display_name": "Sam edited", "party_size": 3, "help_choices": []},
    )
    db = SessionLocal()
    try:
        after = db.query(EmailDispatch).filter(EmailDispatch.event_id == event["id"]).count()
    finally:
        db.close()
    assert after == before  # edit didn't touch the email side at all


def test_event_bad_token_404(client):
    assert client.get("/api/v1/events/by-token/nope").status_code == 404


# --- withdraw (participant deletes their own submission) --------------


def test_form_withdraw(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    token = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 3}]},
    ).json()["edit_token"]

    assert client.post(f"/api/v1/forms/by-token/{token}/withdraw").status_code == 204
    # Submission + its responses are gone; the token no longer resolves.
    assert client.get(f"/api/v1/forms/by-token/{token}").status_code == 404
    summary = client.get(f"/api/v1/forms/{form['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 0


def test_datepoll_withdraw(client, organiser_headers):
    poll = _create_poll(client, organiser_headers)
    d0 = poll["slots"][0]["id"]
    token = client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"datepoll_slot_id": d0, "availability": "yes"}]},
    ).json()["edit_token"]

    assert client.post(f"/api/v1/datepolls/by-token/{token}/withdraw").status_code == 204
    assert client.get(f"/api/v1/datepolls/by-token/{token}").status_code == 404
    summary = client.get(f"/api/v1/datepolls/{poll['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 0


def test_event_withdraw_deletes_signup(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    token = client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 2, "help_choices": []},
    ).json()["edit_token"]

    assert client.post(f"/api/v1/events/by-token/{token}/withdraw").status_code == 204
    assert client.get(f"/api/v1/events/by-token/{token}").status_code == 404


def test_event_withdraw_leaves_email_dispatches_intact(client, organiser_headers):
    from backend.database import SessionLocal
    from backend.models import EmailDispatch

    event = _create_event(client, organiser_headers)
    token = client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "email": "sam@local.dev"},
    ).json()["edit_token"]

    db = SessionLocal()
    try:
        before = db.query(EmailDispatch).filter(EmailDispatch.event_id == event["id"]).count()
    finally:
        db.close()
    assert before >= 1  # feedback dispatch created at signup

    assert client.post(f"/api/v1/events/by-token/{token}/withdraw").status_code == 204

    # Withdrawing the signup leaves the decoupled dispatch rows alone, by
    # design (no signup_id link) — the person may still get the email.
    db = SessionLocal()
    try:
        after = db.query(EmailDispatch).filter(EmailDispatch.event_id == event["id"]).count()
    finally:
        db.close()
    assert after == before


def test_withdraw_bad_token_404(client):
    assert client.post("/api/v1/forms/by-token/nope/withdraw").status_code == 404
    assert client.post("/api/v1/datepolls/by-token/nope/withdraw").status_code == 404
    assert client.post("/api/v1/events/by-token/nope/withdraw").status_code == 404


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
    old = client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 2, "help_choices": []},
    ).json()["edit_token"]
    rows = client.get(f"/api/v1/events/{event['id']}/signups", headers=organiser_headers).json()
    assert rows[0]["link_recovered_at"] is None
    fresh = _recover(client, organiser_headers, f"/api/v1/events/{event['id']}/signups/{rows[0]['id']}/edit-link")

    assert client.get(f"/api/v1/events/by-token/{old}").status_code == 404  # old link dead
    page = client.get(f"/api/v1/events/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None
    rows = client.get(f"/api/v1/events/{event['id']}/signups", headers=organiser_headers).json()
    assert rows[0]["link_recovered_at"] is not None


def test_event_recovery_stamp_survives_edits_and_updates_on_recopy(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "help_choices": []},
    )
    sid = client.get(f"/api/v1/events/{event['id']}/signups", headers=organiser_headers).json()[0]["id"]
    path = f"/api/v1/events/{event['id']}/signups/{sid}/edit-link"
    token = _recover(client, organiser_headers, path)
    first = client.get(f"/api/v1/events/by-token/{token}").json()["link_recovered_at"]

    # The participant editing their signup never clears the stamp.
    r = client.put(
        f"/api/v1/events/by-token/{token}",
        json={"display_name": "Sam", "party_size": 3, "help_choices": []},
    )
    assert r.status_code == 200 and r.json()["link_recovered_at"] == first

    # A second recovery moves the stamp forward (banner shows the latest).
    token2 = _recover(client, organiser_headers, path)
    second = client.get(f"/api/v1/events/by-token/{token2}").json()["link_recovered_at"]
    assert second >= first


def test_event_recovery_requires_auth_and_scope(client, organiser_headers):
    event = _create_event(client, organiser_headers)
    client.post(
        f"/api/v1/events/by-slug/{event['slug']}/signups",
        json={"display_name": "Sam", "party_size": 1, "help_choices": []},
    )
    sid = client.get(f"/api/v1/events/{event['id']}/signups", headers=organiser_headers).json()[0]["id"]
    assert client.post(f"/api/v1/events/{event['id']}/signups/{sid}/edit-link").status_code == 401
    r = client.post(f"/api/v1/events/{event['id']}/signups/does-not-exist/edit-link", headers=organiser_headers)
    assert r.status_code == 404


def test_form_recovery_rotates_and_stamps(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    qid = form["questions"][0]["id"]
    old = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 3}]},
    ).json()["edit_token"]
    subs = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["link_recovered_at"] is None
    fresh = _recover(
        client, organiser_headers, f"/api/v1/forms/{form['id']}/submissions/{subs[0]['submission_id']}/edit-link"
    )

    assert client.get(f"/api/v1/forms/by-token/{old}").status_code == 404
    page = client.get(f"/api/v1/forms/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None
    subs = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["link_recovered_at"] is not None


def test_datepoll_recovery_rotates_and_stamps(client, organiser_headers):
    poll = _create_poll(client, organiser_headers)
    d0 = poll["slots"][0]["id"]
    old = client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"datepoll_slot_id": d0, "availability": "yes"}]},
    ).json()["edit_token"]
    subs = client.get(f"/api/v1/datepolls/{poll['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["link_recovered_at"] is None
    fresh = _recover(
        client, organiser_headers, f"/api/v1/datepolls/{poll['id']}/submissions/{subs[0]['submission_id']}/edit-link"
    )

    assert client.get(f"/api/v1/datepolls/by-token/{old}").status_code == 404
    page = client.get(f"/api/v1/datepolls/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None


def test_chore_recovery_rotates_and_stamps(client, organiser_headers):
    body = {
        "chapter_id": _chapter_id(client, organiser_headers),
        "name": "EL roster",
        "starts_on": "2027-01-04",
        "chores": [{"name": "Bins", "cycle_slots": [2]}],
    }
    roster = client.post("/api/v1/chores", headers=organiser_headers, json=body).json()
    old = client.post(
        f"/api/v1/chores/by-slug/{roster['slug']}/enroll",
        json={"display_name": "Sam", "chore_ids": [roster["chores"][0]["id"]]},
    ).json()["edit_token"]
    vols = client.get(f"/api/v1/chores/{roster['id']}/volunteers", headers=organiser_headers).json()
    assert vols[0]["link_recovered_at"] is None
    fresh = _recover(client, organiser_headers, f"/api/v1/chores/{roster['id']}/volunteers/{vols[0]['id']}/edit-link")

    assert client.get(f"/api/v1/chores/by-token/{old}").status_code == 404
    page = client.get(f"/api/v1/chores/by-token/{fresh}")
    assert page.status_code == 200 and page.json()["link_recovered_at"] is not None
    vols = client.get(f"/api/v1/chores/{roster['id']}/volunteers", headers=organiser_headers).json()
    assert vols[0]["link_recovered_at"] is not None
