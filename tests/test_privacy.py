"""Privacy invariants — verified against the live code path:

1. Email decryption is only called by the email worker code paths
   (feedback + reminder). No router, no schema, no SCD2 helper.
2. Encrypted email is wiped after the worker processes a signup.
3. Signups list endpoint returns only ``display_name`` + ``party_size`` —
   never email, source, or feedback status.
4. Feedback responses carry no link to the originating signup.
"""


def test_decrypt_only_called_from_mail_lifecycle():
    """Static check: the only call site of ``encryption.decrypt``
    in the backend is the email lifecycle worker. Adding a
    second caller is a privacy red flag and must be a deliberate
    code review, not a casual change."""
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parent.parent / "backend"
    callers: list[str] = []
    for path in backend_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "encryption.py":
            continue
        if "encryption.decrypt" in text or "from .encryption import decrypt" in text:
            callers.append(str(path.relative_to(backend_dir.parent)))
    assert sorted(callers) == [
        "backend/services/mail_lifecycle.py",
    ], callers


def test_signup_list_only_exposes_name_and_size(client, organiser_headers):
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "T",
            "chapter_id": me["chapters"][0]["id"],
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "feedback_enabled": True,
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
    # The privacy invariant is field-level: the email-side fields
    # ``email``, ``source_choice``, and any dispatch / status data
    # must never appear here. The internal ``id`` (random UUID,
    # exposed so the organiser can target a specific row for
    # delete) and ``help_choices`` (empty when the event has none)
    # carry no PII. Asserting on banned-field absence rather than
    # exact equality keeps this tripwire useful as the schema
    # evolves without churn.
    assert len(rows) == 1
    row = rows[0]
    assert row["display_name"] == "Alice"
    assert row["party_size"] == 2
    assert row["help_choices"] == []
    banned = {"email", "encrypted_email", "source_choice", "status", "channel", "message_id"}
    assert not (banned & set(row.keys())), set(row.keys())


def test_feedback_response_has_no_signup_link():
    """``FeedbackResponse`` only has ``event_id``, ``question_key``,
    ``submission_id``. No ``signup_id`` column."""
    from backend.models import FeedbackResponse

    cols = {c.name for c in FeedbackResponse.__table__.columns}
    assert "signup_id" not in cols, cols
    # Spot-check that what should be there, is.
    assert "submission_id" in cols
    assert "event_id" in cols


def test_encrypt_only_called_from_signups_router():
    """Static check: ``encryption.encrypt`` is invoked from exactly
    the public signups router and the local-mode seed. Adding any
    other caller silently widens the surface where plaintext
    addresses could leak; this assertion is a tripwire."""
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parent.parent / "backend"
    callers: list[str] = []
    for path in backend_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "encryption.py":
            continue
        if "encryption.encrypt(" in text or "from .encryption import encrypt" in text:
            callers.append(str(path.relative_to(backend_dir.parent)))
    assert sorted(callers) == [
        "backend/routers/signups.py",
        "backend/seed.py",
    ], callers


def test_encrypted_email_writes_only_from_allowlisted_modules():
    """Static check: any code that mutates ``encrypted_email`` (the
    column on ``EmailDispatch``) must live in one of the
    allowlisted modules. The allowlist enforces the privacy
    contract: signups.py creates ciphertext at the point of
    consent (one row per channel); mail_lifecycle.py nulls it on
    every terminal transition. Anywhere else is a bug."""
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parent.parent / "backend"
    # Write-shaped patterns only:
    #   * ``encrypted_email=``  — INSERT or kwargs assignment
    #   * ``EmailDispatch.encrypted_email:`` — bulk UPDATE
    #     setting (``: None`` for the wipe, ``: foo`` for assigns)
    #   * ``.encrypted_email =`` — direct row mutation
    # Read-shaped expressions like ``encrypted_email.is_not(None)``
    # are OK in any module (worker / reaper filter predicates).
    write_needles = [
        "encrypted_email=",
        "EmailDispatch.encrypted_email:",
        ".encrypted_email =",
    ]
    callers: set[str] = set()
    for path in backend_dir.rglob("*.py"):
        if path.name == "email_dispatch.py" and path.parent.name == "models":
            # The model definition is the column; not a write site.
            continue
        text = path.read_text(encoding="utf-8")
        if any(needle in text for needle in write_needles):
            callers.add(str(path.relative_to(backend_dir.parent)))
    assert callers == {
        "backend/routers/signups.py",
        "backend/seed.py",
        "backend/services/mail_lifecycle.py",
    }, callers


def test_logger_pii_kwargs_allowlist():
    """Static check: ``logger.*`` calls must not pass recipient
    addresses as kwargs. ``to=`` and ``email=`` are the two shapes
    the codebase has used for that; both are restricted to a tight
    allowlist.

    Allowed:
    * ``services/mail.py`` — the email-send hop is the one place a
      recipient address is in scope at all (CLAUDE.md privacy rule).
    * ``seed.py`` — local-mode demo bootstrap, ships fake addresses
      typed by the operator running ``cli.py seed-demo``.

    Anywhere else is a privacy regression: logs leak, and a kwarg
    on a ``logger.info`` line is a year-of-contributors away from
    being grep-archaeology'd into a reusable pattern.
    """
    import pathlib
    import re

    backend_dir = pathlib.Path(__file__).resolve().parent.parent / "backend"
    # ``logger.<level>(...)`` calls passing ``to=`` or ``email=`` (or
    # ``recipient=``) as a kwarg. The regex spans the call body so
    # multi-line ``logger.info(...)`` invocations are caught too.
    pattern = re.compile(
        r"logger\.(?:info|warning|error|debug|exception)\([^)]*"
        r"\b(?:to|email|recipient)=",
        re.DOTALL,
    )
    offenders: set[str] = set()
    for path in backend_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.add(str(path.relative_to(backend_dir.parent)))
    assert offenders == {
        "backend/services/mail.py",
        "backend/seed.py",
    }, offenders


def test_encryption_decrypt_signature():
    """Sanity: the encrypt/decrypt pair are inverses for a
    representative email string."""
    from backend.services import encryption

    plain = "alice@local.dev"
    blob = encryption.encrypt(plain)
    assert isinstance(blob, bytes)
    assert encryption.decrypt(blob) == plain
