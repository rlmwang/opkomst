"""Auth flow: magic-link login + magic-link registration completion.

The endpoint surface is two-door-but-one-form:

* ``POST /auth/login-link`` accepts an email, returns the same
  ``LinkSent`` body whether the email is registered or not.
* If the email matches a live user it gets a ``LoginToken``,
  redeemed at ``POST /auth/login`` for a JWT.
* If the email is unknown it gets a ``RegistrationToken``,
  redeemed at ``POST /auth/complete-registration`` (token + name)
  for a JWT — completing sign-up logs the user in in the same step.

Bootstrap-admin carve-out, soft-delete restore, race recovery on
the partial-unique email index and JWT-secret/expiry rejection
are all covered here.
"""

from backend.database import SessionLocal
from backend.models import LoginToken, RegistrationToken, User
from tests._helpers.users import register_user


def _latest_login_token() -> str:
    db = SessionLocal()
    try:
        row = db.query(LoginToken).order_by(LoginToken.created_at.desc()).first()
        assert row is not None
        return row.token
    finally:
        db.close()


def _latest_registration_token(email: str) -> str:
    db = SessionLocal()
    try:
        row = (
            db.query(RegistrationToken)
            .filter(RegistrationToken.email == email)
            .order_by(RegistrationToken.created_at.desc())
            .first()
        )
        assert row is not None
        return row.token
    finally:
        db.close()


# ---- Bootstrap admin ---------------------------------------------


def test_bootstrap_admin_auto_approves(client, admin_token):
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "admin@local.dev"
    assert me["role"] == "admin"
    assert me["is_approved"] is True


def test_complete_registration_returns_jwt_and_logs_user_in(client):
    """Completing registration is the user's first sign-in: the
    response carries a JWT plus the freshly-created user row, no
    separate /auth/login round-trip required."""
    r = client.post("/api/v1/auth/login-link", json={"email": "first@local.dev"})
    assert r.status_code == 200
    raw = _latest_registration_token("first@local.dev")

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "First"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == "first@local.dev"
    assert body["user"]["role"] == "organiser"
    assert body["user"]["is_approved"] is False  # admin still gates


# ---- /login-link branching ---------------------------------------


def test_login_link_known_email_sends_login_email(client, admin_token, monkeypatch):
    """Known email gets ``login.html``, not ``register_complete.html``."""
    sent: list[tuple[str, str]] = []

    def _capture(to: str, template_name: str, context, locale="nl") -> None:  # noqa: ANN001
        sent.append((to, template_name))

    monkeypatch.setattr("backend.routers.auth.send_email", _capture)

    r = client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})
    assert r.status_code == 200
    assert sent == [("admin@local.dev", "login.html")]


def test_login_link_unknown_email_sends_register_complete_email(client, monkeypatch):
    """Unknown email gets ``register_complete.html`` and a fresh
    ``RegistrationToken`` row exists for the address."""
    sent: list[tuple[str, str]] = []

    def _capture(to: str, template_name: str, context, locale="nl") -> None:  # noqa: ANN001
        sent.append((to, template_name))

    monkeypatch.setattr("backend.routers.auth.send_email", _capture)

    r = client.post("/api/v1/auth/login-link", json={"email": "ghost@local.dev"})
    assert r.status_code == 200
    assert sent == [("ghost@local.dev", "register_complete.html")]

    db = SessionLocal()
    try:
        row = db.query(RegistrationToken).filter(RegistrationToken.email == "ghost@local.dev").first()
        assert row is not None
    finally:
        db.close()


def test_login_link_response_shape_identical_for_known_and_unknown(client, admin_token):
    """The privacy invariant: /login-link can't be probed for whether
    an email is registered. Both branches return the same body."""
    known = client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})
    unknown = client.post("/api/v1/auth/login-link", json={"email": "nobody@local.dev"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_login_link_repeated_unknown_email_replaces_old_token(client, monkeypatch):
    """A user who clicks "send link" twice should expect the latest
    email's link to work — not a stale one from the first click.
    The second mint deletes the prior row so only one outstanding
    token per email exists."""
    monkeypatch.setattr("backend.routers.auth.send_email", lambda **kw: None)

    client.post("/api/v1/auth/login-link", json={"email": "twice@local.dev"})
    first_raw = _latest_registration_token("twice@local.dev")

    client.post("/api/v1/auth/login-link", json={"email": "twice@local.dev"})
    second_raw = _latest_registration_token("twice@local.dev")
    assert first_raw != second_raw

    db = SessionLocal()
    try:
        rows = db.query(RegistrationToken).filter(RegistrationToken.email == "twice@local.dev").all()
        assert len(rows) == 1
        assert rows[0].token == second_raw
    finally:
        db.close()

    # The first link is now dead.
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": first_raw, "name": "Twice"},
    )
    assert r.status_code == 410


# ---- /complete-registration: edge cases --------------------------


def test_complete_registration_invalid_token(client):
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": "not-a-real-token", "name": "X"},
    )
    assert r.status_code == 410


def test_complete_registration_replay_blocked(client):
    client.post("/api/v1/auth/login-link", json={"email": "replay@local.dev"})
    raw = _latest_registration_token("replay@local.dev")

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "Replay"},
    )
    assert r.status_code == 200

    # Second use → 410 Gone, regardless of the name supplied.
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "Replay"},
    )
    assert r.status_code == 410


def test_complete_registration_expired_token(client):
    """Expired token: 410 + the row is cleaned up so it doesn't
    pile up. Mirrors /auth/login's expired-token behaviour."""
    from datetime import UTC, datetime, timedelta

    db = SessionLocal()
    try:
        db.add(
            RegistrationToken(
                token="expired-reg-token",
                email="late@local.dev",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": "expired-reg-token", "name": "Late"},
    )
    assert r.status_code == 410

    db = SessionLocal()
    try:
        assert db.query(RegistrationToken).filter(RegistrationToken.token == "expired-reg-token").first() is None
    finally:
        db.close()


def test_complete_registration_blank_name_rejected(client):
    """``name`` is the only field the user supplies at completion;
    a blank or whitespace-only value would create a useless user
    row, so the endpoint 422s before redeeming the token."""
    client.post("/api/v1/auth/login-link", json={"email": "blank@local.dev"})
    raw = _latest_registration_token("blank@local.dev")

    # Empty string fails Pydantic ``min_length=1``.
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": ""},
    )
    assert r.status_code == 422

    # Whitespace-only fails the explicit strip-then-check in the
    # router; matters because Pydantic's ``min_length`` doesn't
    # strip.
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "   "},
    )
    assert r.status_code == 422

    # Token wasn't consumed — the legitimate retry still works.
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "Real Name"},
    )
    assert r.status_code == 200


def test_complete_registration_strips_whitespace_in_name(client):
    client.post("/api/v1/auth/login-link", json={"email": "trim@local.dev"})
    raw = _latest_registration_token("trim@local.dev")

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "   Trimmed   "},
    )
    assert r.status_code == 200
    assert r.json()["user"]["name"] == "Trimmed"


def test_complete_registration_when_email_already_registered(client, admin_token):
    """A token minted for an email that became registered between
    mint and redeem must 410, not silently overwrite or duplicate
    the existing user. Defensive against a guessed-token attack
    racing a legitimate registration."""
    # Force-create a stale registration token for an email that
    # already has a live user.
    from datetime import UTC, datetime, timedelta

    db = SessionLocal()
    try:
        db.add(
            RegistrationToken(
                token="stale-token",
                email="admin@local.dev",
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": "stale-token", "name": "Imposter"},
    )
    assert r.status_code == 410

    # The original admin row is intact.
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin@local.dev", User.deleted_at.is_(None)).first()
        assert user is not None
        assert user.name == "Admin"
        # Token was cleaned up.
        assert db.query(RegistrationToken).filter(RegistrationToken.token == "stale-token").first() is None
    finally:
        db.close()


# ---- Bootstrap carve-out -----------------------------------------


def test_bootstrap_admin_auto_approved_via_complete_registration(client):
    """First completion matching ``BOOTSTRAP_ADMIN_EMAIL`` lands as
    ``role=admin, is_approved=true``. (Same path admin_token uses,
    asserted explicitly here.)"""
    client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})
    raw = _latest_registration_token("admin@local.dev")
    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "Admin"},
    )
    assert r.status_code == 200
    me = r.json()["user"]
    assert me["role"] == "admin"
    assert me["is_approved"] is True


def test_bootstrap_only_promotes_first_completion(client, admin_token):
    """Once the bootstrap admin exists, a second completion using
    the bootstrap email is impossible — /login-link returns the
    login branch. Asserts the carve-out doesn't fire twice."""
    sent: list[tuple[str, str]] = []
    import backend.routers.auth as auth_module

    real = auth_module.send_email

    def _capture(**kwargs):  # noqa: ANN001, ANN201
        sent.append((kwargs["to"], kwargs["template_name"]))
        return real(**kwargs)

    # Replace with a recorder that still calls through. Order
    # matters: ``send_email`` is referenced at call site.

    import unittest.mock as _mock

    with _mock.patch("backend.routers.auth.send_email", side_effect=_capture):
        r = client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})
        assert r.status_code == 200

    assert sent == [("admin@local.dev", "login.html")]


# ---- Soft-delete restore -----------------------------------------


def test_soft_deleted_email_restores_via_complete_registration(client, admin_headers):
    """Re-registering a soft-deleted email un-deletes the row in
    place (same ``user.id``, name overwritten, role reset to
    organiser, ``is_approved`` reset to false)."""
    uid = register_user(client, "rejoin@local.dev", "Re")

    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    assert r.status_code == 204

    # Re-register through the new flow.
    uid_after = register_user(client, "rejoin@local.dev", "Re-back")
    assert uid_after == uid  # restored in place

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "rejoin@local.dev", User.deleted_at.is_(None)).first()
        assert user is not None
        assert user.id == uid
        assert user.name == "Re-back"
        assert user.role == "organiser"
        assert user.is_approved is False
    finally:
        db.close()


# ---- Race recovery on the partial-unique index -------------------


def test_complete_registration_race_against_concurrent_completion(client, monkeypatch):
    """Two concurrent /complete-registration calls for the same
    email must not both succeed: the partial-unique
    ``uq_users_email_live`` index serialises them. The loser sees
    410, not 500.

    Simulated by having ``_create_fresh_with_race_recovery`` commit
    a rival User row from a separate session right before its own
    INSERT, forcing the IntegrityError fallback."""
    import backend.routers.auth as auth_module

    monkeypatch.setattr(auth_module, "send_email", lambda **kw: None)

    client.post("/api/v1/auth/login-link", json={"email": "race@local.dev"})
    raw = _latest_registration_token("race@local.dev")

    real = auth_module._create_fresh_with_race_recovery
    raced: dict[str, bool] = {"done": False}

    def _commit_rival_then_create(db, email, name):  # noqa: ANN001, ANN201
        if not raced["done"] and email == "race@local.dev":
            raced["done"] = True
            rival = SessionLocal()
            try:
                rival.add(
                    User(
                        email=email,
                        name="Winner",
                        role="organiser",
                        is_approved=False,
                    )
                )
                rival.commit()
            finally:
                rival.close()
        return real(db, email, name)

    monkeypatch.setattr(auth_module, "_create_fresh_with_race_recovery", _commit_rival_then_create)

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": "Loser"},
    )
    assert r.status_code == 410, r.text

    # The winning row is the one that's live, and the registration
    # token was cleaned up.
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "race@local.dev", User.deleted_at.is_(None)).first()
        assert user is not None
        assert user.name == "Winner"
        assert db.query(RegistrationToken).filter(RegistrationToken.token == raw).first() is None
    finally:
        db.close()


# ---- /auth/login (existing user redeem) --------------------------


def test_login_link_then_redeem(client, admin_token):
    r = client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})
    assert r.status_code == 200
    raw = _latest_login_token()

    r = client.post("/api/v1/auth/login", json={"token": raw})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_login_token_is_single_use(client, admin_token):
    client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})
    raw = _latest_login_token()
    assert client.post("/api/v1/auth/login", json={"token": raw}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"token": raw}).status_code == 410


def test_login_rejects_expired_token(client, admin_token):
    from datetime import UTC, datetime, timedelta

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin@local.dev", User.deleted_at.is_(None)).first()
        assert user is not None
        db.add(
            LoginToken(
                token="expired-token",
                user_id=user.id,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.post("/api/v1/auth/login", json={"token": "expired-token"})
    assert r.status_code == 410

    db = SessionLocal()
    try:
        assert db.query(LoginToken).filter(LoginToken.token == "expired-token").first() is None
    finally:
        db.close()


def test_login_rejects_token_for_archived_user(client, admin_token, admin_headers):
    """Archive a user between minting and redeeming a token. The
    redeem path 410s instead of issuing a JWT for a deleted row."""
    uid = register_user(client, "ghost@local.dev", "Ghost")
    client.post("/api/v1/auth/login-link", json={"email": "ghost@local.dev"})
    raw = _latest_login_token()

    assert client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers).status_code == 204

    r = client.post("/api/v1/auth/login", json={"token": raw})
    assert r.status_code == 410


# ---- JWT shape / lifecycle ---------------------------------------


def test_jwt_id_stable_across_user_updates(client, admin_headers, chapter_id):
    """JWT signs ``user.id``; admin actions on the user mustn't
    invalidate previously-minted tokens."""
    uid = register_user(client, "x@local.dev", "X")

    from backend.auth import create_token

    token = create_token(uid)
    client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={"chapter_id": chapter_id},
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == uid


def test_jwt_with_invalid_signature_rejected(client):
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    payload = {
        "sub": "fake-user",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    forged = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_jwt_expired_rejected(client, admin_token):
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from backend.config import settings

    payload = {
        "sub": "any-id",
        "iat": datetime.now(UTC) - timedelta(hours=2),
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    expired = pyjwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_jwt_round_trip_uses_pyjwt(client, organiser_headers):
    import jwt as pyjwt

    from backend.auth import JWT_ALGORITHM, create_token
    from backend.config import settings

    token = create_token("00000000-0000-0000-0000-000000000000")
    decoded = pyjwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[JWT_ALGORITHM],
    )
    assert decoded["sub"] == "00000000-0000-0000-0000-000000000000"
    assert "iat" in decoded
    assert "exp" in decoded
    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == JWT_ALGORITHM
    assert header["alg"] == "HS256"


def test_jwt_for_archived_user_rejected(client, admin_headers, admin_token):
    uid = register_user(client, "ephemeral@local.dev", "E")

    from backend.auth import create_token

    token = create_token(uid)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    assert client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers).status_code == 204
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---- Restored user + magic link round-trip ----------------------


def test_restored_user_can_log_in_via_magic_link(client, admin_headers):
    """End-to-end: register → admin deletes → re-register (restores
    in place) → /login-link mints a LoginToken (not a registration
    token, because the row is now live) → redeem → fresh JWT
    against the restored ``user.id``."""
    uid = register_user(client, "phoenix@local.dev", "Phoenix")
    assert client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers).status_code == 204

    uid_after = register_user(client, "phoenix@local.dev", "Phoenix-back")
    assert uid_after == uid  # restored in place

    assert client.post("/api/v1/auth/login-link", json={"email": "phoenix@local.dev"}).status_code == 200

    raw = _latest_login_token()
    r = client.post("/api/v1/auth/login", json={"token": raw})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == uid
    assert body["user"]["is_approved"] is False  # gate re-required after restore


# ---- Validation + rate limit -------------------------------------


def test_login_link_rejects_malformed_email(client):
    r = client.post("/api/v1/auth/login-link", json={"email": "not-an-email"})
    assert r.status_code == 422


# ---- /me chapter projection -------------------------------------


def test_me_returns_chapters_sorted_by_name(client, admin_headers, admin_token):
    """`/me` projects ``user.chapters`` as a list sorted by name —
    the frontend's chip cluster relies on the order being stable
    across reloads."""
    # Three chapters in deliberately scrambled creation order.
    for name in ("Zwolle", "Amsterdam", "Maastricht"):
        client.post("/api/v1/chapters", headers=admin_headers, json={"name": name})

    db = SessionLocal()
    try:
        from backend.models import Chapter

        admin = db.query(User).filter(User.email == "admin@local.dev", User.deleted_at.is_(None)).first()
        assert admin is not None
        chapter_ids = [c.id for c in db.query(Chapter).filter(Chapter.deleted_at.is_(None)).all()]
    finally:
        db.close()

    r = client.post(
        f"/api/v1/admin/users/{admin.id}/set-chapters",
        headers=admin_headers,
        json={"chapter_ids": chapter_ids},
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["chapters"]]
    assert names == sorted(names, key=str.lower)


def test_me_excludes_soft_deleted_chapter_membership(client, admin_headers):
    """A user can be in a chapter that's later archived — the
    membership row stays so a chapter restore brings the user
    back, but `/me` drops it from the live projection."""
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Tilburg"})
    tilburg_id = r.json()["id"]

    from backend.auth import create_token

    uid = register_user(client, "tilburger@local.dev", "Tilly")
    client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={"chapter_ids": [tilburg_id]},
    )
    user_token = create_token(uid)

    # Archive the chapter; the membership row should silently drop
    # from the user's effective projection.
    client.delete(f"/api/v1/chapters/{tilburg_id}", headers=admin_headers)

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    assert r.json()["chapters"] == []


def test_login_link_rate_limit(client, monkeypatch):
    """5/hour on /login-link — sixth from the same IP gets 429.
    Replaces the previous /register rate-limit test, since
    /register no longer exists."""
    monkeypatch.setattr("backend.routers.auth.send_email", lambda **kw: None)
    for i in range(5):
        r = client.post("/api/v1/auth/login-link", json={"email": f"rl{i}@local.dev"})
        assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login-link", json={"email": "rl-over@local.dev"})
    assert r.status_code == 429
