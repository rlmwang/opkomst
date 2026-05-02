"""Coverage for ``backend/routers/feedback.py``.

The feedback module is the largest router by responsibility:
public form + token redemption, organiser summary with email
health, organiser per-submission CSV source. Pre-R2 it sits
behind ``access.get_event_for_user`` (chapter scoping) which
will simplify post-refactor; the user-visible response shapes
must not change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from uuid_utils import uuid7

from backend.database import SessionLocal
from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    FeedbackResponse,
    FeedbackToken,
    Signup,
)

# The five fixed feedback questions are Python constants
# (``backend.services.feedback_questions``); no seed required.


def _new_event(client: Any, organiser_headers: Any, **overrides: Any) -> dict[str, Any]:
    if "chapter_id" not in overrides:
        me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
        overrides["chapter_id"] = me["chapters"][0]["id"]
    payload = {
        "name": "Demo",
        "topic": None,
        "location": "Adam",
        "starts_at": "2026-05-01T18:00:00",
        "ends_at": "2026-05-01T20:00:00",
        "source_options": ["Flyer"],
        "feedback_enabled": True,
        "locale": "nl",
        **overrides,
    }
    r = client.post("/api/v1/events", headers=organiser_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_signup_with_token(event_id: str, *, email: str = "alice@x.test") -> tuple[str, str]:
    """Insert a Signup + FeedbackToken pair directly. Returns
    ``(token, signup_id)``. The signup row is independent from
    the token (privacy: a feedback response can't be linked to
    a signup); ``email`` is unused under R5 because the address
    no longer lives on the signup."""
    del email  # legacy argument; address lives on dispatch rows now
    db = SessionLocal()
    try:
        signup = Signup(
            event_id=event_id,
            display_name="Alice",
            party_size=1,
            source_choice="Flyer",
            help_choices=[],
        )
        db.add(signup)
        db.flush()
        raw = f"tok-{uuid7()}"
        db.add(
            FeedbackToken(
                token=raw,
                event_id=event_id,
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
        db.commit()
        return raw, signup.id
    finally:
        db.close()


# --- /feedback/questions -------------------------------------------


def test_questions_list_returns_five_in_order(client, organiser_headers):
    r = client.get("/api/v1/feedback/questions", headers=organiser_headers)
    assert r.status_code == 200
    rows = r.json()
    # Seed populates exactly five fixed questions.
    assert len(rows) == 5
    keys = [q["key"] for q in rows]
    assert keys == ["q1_overall", "q2_recommend", "q3_welcome", "q4_better", "q5_anything_else"]


def test_questions_list_requires_approved_user(client):
    r = client.get("/api/v1/feedback/questions")
    assert r.status_code == 401


# --- /feedback/{token} ---------------------------------------------


def test_feedback_form_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])

    r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 200
    body = r.json()
    assert body["event_name"] == event["name"]
    assert body["event_slug"] == event["slug"]
    assert body["event_locale"] == "nl"
    assert len(body["questions"]) == 5


def test_feedback_form_unknown_token_410s(client):
    r = client.get("/api/v1/feedback/no-such-token")
    assert r.status_code == 410


def test_feedback_form_still_works_after_event_archive(client, organiser_headers):
    """Design choice: the feedback token bearer earned their
    right to submit when the email was sent. An organiser
    archiving the event mid-flight does not retroactively revoke
    in-flight tokens — the token holder can still load and
    submit the form. Public preview endpoints DO 404 on archived
    events (see ``test_public_archived.py``); the difference is
    that those have no token gate."""
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    client.post(f"/api/v1/events/{event['id']}/archive", headers=organiser_headers)

    r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 200


# --- /feedback/{token}/submit --------------------------------------


def test_submit_feedback_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    questions = client.get("/api/v1/feedback/questions", headers=organiser_headers).json()

    answers = []
    for q in questions:
        if q["kind"] == "rating":
            answers.append({"question_key": q["key"], "answer_int": 4})
        else:
            answers.append({"question_key": q["key"], "answer_text": "Nice"})

    r = client.post(f"/api/v1/feedback/{raw}/submit", json={"answers": answers})
    assert r.status_code == 201

    # Token deleted (single-use).
    r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 410

    # Responses landed.
    db = SessionLocal()
    try:
        rows = db.query(FeedbackResponse).filter(FeedbackResponse.event_id == event["id"]).all()
        assert len(rows) == 5
        # All rows share one submission_id (random per submission).
        sub_ids = {r.submission_id for r in rows}
        assert len(sub_ids) == 1
    finally:
        db.close()


def test_submit_feedback_unknown_question_id_400s(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    r = client.post(
        f"/api/v1/feedback/{raw}/submit",
        json={"answers": [{"question_key": "no-such", "answer_int": 5}]},
    )
    assert r.status_code == 400


def test_submit_feedback_missing_required_400s(client, organiser_headers):
    """The first three questions are ``required=True``; submitting
    without them must 400."""
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    r = client.post(f"/api/v1/feedback/{raw}/submit", json={"answers": []})
    assert r.status_code == 400


def test_submit_already_redeemed_token_410s(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    questions = client.get("/api/v1/feedback/questions", headers=organiser_headers).json()
    answers = [{"question_key": q["key"], "answer_int": 5} for q in questions if q["kind"] == "rating"]
    assert client.post(f"/api/v1/feedback/{raw}/submit", json={"answers": answers}).status_code == 201
    # Replay → 410 (token deleted on first redeem).
    r = client.post(f"/api/v1/feedback/{raw}/submit", json={"answers": answers})
    assert r.status_code == 410


# --- /events/{id}/feedback-summary ---------------------------------


def test_feedback_summary_empty_event(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.get(
        f"/api/v1/events/{event['id']}/feedback-summary",
        headers=organiser_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["submission_count"] == 0
    assert body["signup_count"] == 0
    assert body["response_rate"] == 0.0
    assert len(body["questions"]) == 5
    # Email health: every channel reports zero counts.
    for ch in body["email_health"]:
        for key in ("pending", "sent", "failed", "not_applicable"):
            assert body["email_health"][ch][key] == 0


def test_feedback_summary_with_responses(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    questions = client.get("/api/v1/feedback/questions", headers=organiser_headers).json()
    answers = [{"question_key": q["key"], "answer_int": 4} for q in questions if q["kind"] == "rating"] + [
        {"question_key": q["key"], "answer_text": "Goed!"} for q in questions if q["kind"] == "text"
    ]
    client.post(f"/api/v1/feedback/{raw}/submit", json={"answers": answers})

    r = client.get(
        f"/api/v1/events/{event['id']}/feedback-summary",
        headers=organiser_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["submission_count"] == 1
    assert body["signup_count"] == 1
    assert body["response_rate"] == 1.0

    rating_qs = [q for q in body["questions"] if q["kind"] == "rating"]
    assert all(q["response_count"] == 1 for q in rating_qs)
    # All ratings were 4, so distribution[3] == 1, others 0.
    for q in rating_qs:
        assert q["rating_distribution"] == [0, 0, 0, 1, 0]
        assert q["rating_average"] == 4.0


def test_feedback_summary_email_health_counts_dispatches(client, organiser_headers):
    """Insert one signup + one SENT feedback dispatch + one
    PENDING reminder dispatch; the summary should reflect both."""
    event = _new_event(client, organiser_headers, reminder_enabled=True)
    db = SessionLocal()
    try:
        signup = Signup(
            event_id=event["id"],
            display_name="A",
            party_size=1,
            source_choice="Flyer",
            help_choices=[],
        )
        db.add(signup)
        db.add(
            EmailDispatch(
                event_id=event["id"],
                channel=EmailChannel.FEEDBACK,
                status=EmailStatus.SENT,
            )
        )
        db.add(
            EmailDispatch(
                event_id=event["id"],
                channel=EmailChannel.REMINDER,
                status=EmailStatus.PENDING,
                encrypted_email=b"some-ciphertext",
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get(
        f"/api/v1/events/{event['id']}/feedback-summary",
        headers=organiser_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email_health"]["feedback"]["sent"] == 1
    assert body["email_health"]["reminder"]["pending"] == 1


def test_feedback_summary_other_chapter_404s(client, admin_headers, organiser_headers):
    """Organiser can't peek at events outside their chapter."""
    event = _new_event(client, organiser_headers)
    # New chapter + new approved organiser there.
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]

    from backend.auth import create_token
    from tests._helpers.users import register_user

    uid = register_user(client, "outsider@local.dev", "O")
    client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={"chapter_ids": [other_chapter]},
    )
    outsider_token = create_token(uid)

    r = client.get(
        f"/api/v1/events/{event['id']}/feedback-summary",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert r.status_code == 404


# --- /events/{id}/feedback-submissions -----------------------------


def test_feedback_submissions_csv_source(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    raw, _ = _seed_signup_with_token(event["id"])
    questions = client.get("/api/v1/feedback/questions", headers=organiser_headers).json()
    answers = []
    for q in questions:
        if q["kind"] == "rating":
            answers.append({"question_key": q["key"], "answer_int": 5})
        else:
            answers.append({"question_key": q["key"], "answer_text": "Top"})
    client.post(f"/api/v1/feedback/{raw}/submit", json={"answers": answers})

    r = client.get(
        f"/api/v1/events/{event['id']}/feedback-submissions",
        headers=organiser_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    sub = rows[0]
    assert "submission_id" in sub
    # ``answers`` is a key→value map.
    assert sub["answers"]["q1_overall"] == 5
    assert sub["answers"]["q4_better"] == "Top"
