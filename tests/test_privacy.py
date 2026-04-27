"""Privacy invariants — verified against the live code path:

1. Email decryption is only called by the email worker code paths
   (feedback + reminder). No router, no schema, no SCD2 helper.
2. Encrypted email is wiped after the worker processes a signup.
3. Signups list endpoint returns only ``display_name`` + ``party_size`` —
   never email, source, or feedback status.
4. Feedback responses carry no link to the originating signup.
"""


def test_decrypt_only_called_from_email_workers():
    """Static check: the only call sites of ``encryption.decrypt``
    in the backend are the two email workers. Adding a third
    caller is a privacy red flag and must be a deliberate code
    review, not a casual change."""
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parent.parent / "backend"
    callers: list[str] = []
    for path in backend_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # Don't count the definition itself.
        if path.name == "encryption.py":
            continue
        if "encryption.decrypt" in text or "from .encryption import decrypt" in text:
            callers.append(str(path.relative_to(backend_dir.parent)))
    assert sorted(callers) == [
        "backend/services/feedback_worker.py",
        "backend/services/reminder_worker.py",
    ], callers


def test_signup_list_only_exposes_name_and_size(client, organiser_headers):
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "T",
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "questionnaire_enabled": True,
            "locale": "nl",
        },
    )
    eid = r.json()["id"]
    slug = r.json()["slug"]
    client.post(
        f"/api/v1/events/by-slug/{slug}/signups",
        json={
            "display_name": "Alice",
            "party_size": 2,
            "source_choice": "F",
            "email": "alice@local.dev",
        },
    )
    r = client.get(f"/api/v1/events/{eid}/signups", headers=organiser_headers)
    assert r.status_code == 200
    rows = r.json()
    # Help-choices was added in the can-help feature; an empty list
    # is part of the response shape but doesn't carry email / source /
    # status data — the privacy invariant is still upheld.
    assert rows == [{"display_name": "Alice", "party_size": 2, "help_choices": []}]


def test_feedback_response_has_no_signup_link():
    """``FeedbackResponse`` only has ``event_id``, ``question_id``,
    ``submission_id``. No ``signup_id`` column."""
    from backend.models import FeedbackResponse

    cols = {c.name for c in FeedbackResponse.__table__.columns}
    assert "signup_id" not in cols, cols
    # Spot-check that what should be there, is.
    assert "submission_id" in cols
    assert "event_id" in cols


def test_encryption_decrypt_signature():
    """Sanity: the encrypt/decrypt pair are inverses for a
    representative email string."""
    from backend.services import encryption

    plain = "alice@local.dev"
    blob = encryption.encrypt(plain)
    assert isinstance(blob, bytes)
    assert encryption.decrypt(blob) == plain
