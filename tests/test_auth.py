"""Auth flow: bootstrap admin, magic-link redemption, JWT survives
user edits, soft-delete + restore via re-register."""


def test_bootstrap_admin_auto_approves(client, admin_token):
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "admin@local.dev"
    assert me["role"] == "admin"
    assert me["is_approved"] is True


def test_login_link_unknown_email_returns_ok(client):
    """We never reveal whether an email exists — every login-link
    POST returns 200."""
    r = client.post(
        "/api/v1/auth/login-link",
        json={"email": "ghost@local.dev"},
    )
    assert r.status_code == 200


def test_login_link_then_redeem(client, admin_token):
    """Mint a link for a real user, redeem it, expect a fresh JWT."""
    r = client.post(
        "/api/v1/auth/login-link",
        json={"email": "admin@local.dev"},
    )
    assert r.status_code == 200

    # Pull the freshly-minted token out of the DB — the test backend
    # doesn't roundtrip through SMTP.
    from backend.database import SessionLocal
    from backend.models import LoginToken

    db = SessionLocal()
    try:
        row = db.query(LoginToken).order_by(LoginToken.created_at.desc()).first()
        assert row is not None
        raw = row.token
    finally:
        db.close()

    r = client.post("/api/v1/auth/login", json={"token": raw})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_login_token_is_single_use(client, admin_token):
    client.post("/api/v1/auth/login-link", json={"email": "admin@local.dev"})

    from backend.database import SessionLocal
    from backend.models import LoginToken

    db = SessionLocal()
    try:
        row = db.query(LoginToken).order_by(LoginToken.created_at.desc()).first()
        assert row is not None
        raw = row.token
    finally:
        db.close()

    assert client.post("/api/v1/auth/login", json={"token": raw}).status_code == 200
    # Replay → 410 Gone.
    assert client.post("/api/v1/auth/login", json={"token": raw}).status_code == 410


def test_jwt_id_stable_across_user_updates(client, admin_headers, chapter_id):
    """JWT signs ``entity_id``, so it must keep working when the
    user's row id changes (i.e. after any SCD2 update)."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "x@local.dev", "name": "X"},
    )
    assert r.status_code == 201

    from backend.auth import create_token
    from backend.database import SessionLocal
    from backend.models import User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "x@local.dev").first()
        assert user is not None
        uid = user.entity_id
    finally:
        db.close()

    token = create_token(uid)
    client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={"chapter_id": chapter_id},
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == uid


def test_soft_delete_then_restore_via_register(client, admin_headers):
    """Admin deletes a user → reregistering with the same email
    restores the SCD2 chain rather than creating a new one."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "rejoin@local.dev", "name": "Re"},
    )
    assert r.status_code == 201

    from backend.database import SessionLocal
    from backend.models import User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "rejoin@local.dev").first()
        assert user is not None
        uid = user.entity_id
    finally:
        db.close()

    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    assert r.status_code == 204

    # Reregister with same email — should restore the SCD2 chain.
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "rejoin@local.dev", "name": "Re-back"},
    )
    assert r.status_code == 201, r.text

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "rejoin@local.dev").first()
        assert user is not None
        assert user.entity_id == uid  # entity_id preserved
        assert user.is_approved is False  # gate re-required
        assert user.role == "organiser"
    finally:
        db.close()


def test_jwt_with_invalid_signature_rejected(client):
    """A token signed with a different secret must 401. The
    server's secret is loaded at boot via ``settings.jwt_secret``;
    we forge a token with a different key and post it."""
    from datetime import UTC, datetime, timedelta

    from jose import jwt as jose_jwt

    payload = {
        "sub": "fake-user",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    forged = jose_jwt.encode(payload, "wrong-secret", algorithm="HS256")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_jwt_expired_rejected(client, admin_token):
    """A valid signature with ``exp`` in the past must 401.
    Generates a token with the live secret but with ``exp`` an
    hour ago."""
    from datetime import UTC, datetime, timedelta

    from jose import jwt as jose_jwt

    from backend.config import settings

    payload = {
        "sub": "any-id",
        "iat": datetime.now(UTC) - timedelta(hours=2),
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    expired = jose_jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm="HS256"
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_jwt_for_archived_user_rejected(client, admin_headers, admin_token):
    """A previously-valid JWT becomes invalid the moment the user
    is soft-deleted: ``get_current_user`` looks up the
    ``entity_id`` via SCD2 ``current_by_entity``, which returns
    None for a closed chain."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "ephemeral@local.dev", "name": "E"},
    )
    assert r.status_code == 201

    from backend.auth import create_token
    from backend.database import SessionLocal
    from backend.models import User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = (
            scd2.current(db.query(User)).filter(User.email == "ephemeral@local.dev").first()
        )
        assert user is not None
        uid = user.entity_id
    finally:
        db.close()
    token = create_token(uid)
    # Token works while the user is current.
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 200
    )

    # Soft-delete; the same JWT now 401s.
    assert (
        client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers).status_code
        == 204
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_explicit_validation_for_register(client):
    # Email format
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "name": "X"},
    )
    assert r.status_code == 422


def test_register_rate_limit(client):
    """5/hour on register — sixth from the same IP gets 429."""
    for i in range(5):
        r = client.post(
            "/api/v1/auth/register",
            json={"email": f"rl{i}@local.dev", "name": "RL"},
        )
        assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "rl-over@local.dev", "name": "RL"},
    )
    assert r.status_code == 429


def test_bootstrap_promotes_only_first_registration(client, admin_token):
    """Once the bootstrap admin exists, a second registration with
    the same email must NOT re-promote — it lands as an existing
    email (mint-link branch). A third registration with the
    bootstrap email after the admin is soft-deleted goes through
    restore, which strips the admin role by design."""
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.json()["role"] == "admin"

    # Second registration: email exists, mint-link path. Role
    # unchanged.
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "admin@local.dev", "name": "Doppelgänger"},
        ).status_code
        == 201
    )

    from backend.database import SessionLocal
    from backend.models import User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "admin@local.dev").first()
        assert user is not None
        assert user.role == "admin"  # still admin from first registration
        assert user.is_approved is True
    finally:
        db.close()


def test_bootstrap_race_falls_through_to_mint_link(client, monkeypatch):
    """Two simultaneous registrations with the bootstrap email both
    pass the ``count() == 0`` check; the second INSERT collides on
    the partial-unique index ``uq_users_email_current``. The router
    must catch the IntegrityError, treat it as an existing-email
    case, and mint a link to the row that won the race — instead of
    bubbling a 500."""
    from backend.routers import auth as auth_module
    from backend.services import scd2 as scd2_module

    sent: list[tuple[str, str]] = []

    def _capture(to: str, template_name: str, context, locale="nl") -> None:  # noqa: ANN001
        sent.append((to, template_name))

    monkeypatch.setattr(auth_module, "send_email", _capture)

    # Simulate the other process winning the race by committing a
    # competing user from a *separate* session right before the
    # router's INSERT. We hook ``_user_by_email`` to return None on
    # the first call (so the router still believes the email is
    # free), then commit the rival, then let the router's INSERT
    # crash on the partial-unique index.
    from backend.database import SessionLocal

    real_create = scd2_module.scd2_create
    raced: dict[str, bool] = {"done": False}

    def _commit_rival_then_create(db, model, **kwargs):  # noqa: ANN001, ANN201
        if not raced["done"] and kwargs.get("email") == "admin@local.dev":
            raced["done"] = True
            rival = SessionLocal()
            try:
                real_create(rival, model, **{**kwargs, "name": "Winner"})
                rival.commit()
            finally:
                rival.close()
        return real_create(db, model, **kwargs)

    monkeypatch.setattr(auth_module.scd2, "scd2_create", _commit_rival_then_create)

    r = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@local.dev", "name": "Loser"},
    )
    assert r.status_code == 201, r.text
    # Loser branch: sent a fresh login link to the winner.
    assert ("admin@local.dev", "login.html") in sent

    # The winning row is the one that's current.
    from backend.models import User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "admin@local.dev").first()
        assert user is not None
        assert user.name == "Winner"
    finally:
        db.close()


def test_register_existing_email_still_sends_link(client, admin_token, monkeypatch):
    """Privacy carve-out: registering with an already-registered
    email must not 409 (that would leak existence). Instead the
    server mints a fresh login link for the existing account so the
    legitimate owner of the address can always get in."""
    sent: list[tuple[str, str]] = []

    def _capture(to: str, template_name: str, context, locale="nl") -> None:  # noqa: ANN001
        sent.append((to, template_name))

    monkeypatch.setattr("backend.routers.auth.send_email", _capture)

    r = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@local.dev", "name": "Doppelgänger"},
    )
    assert r.status_code == 201, r.text
    assert ("admin@local.dev", "login.html") in sent


def test_login_rejects_expired_token(client, admin_token):
    """A token whose ``expires_at`` is in the past must 410. The
    redeem path also has to delete the row so it doesn't pile up."""
    from datetime import UTC, datetime, timedelta

    from backend.database import SessionLocal
    from backend.models import LoginToken, User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "admin@local.dev").first()
        assert user is not None
        row = LoginToken(
            token="expired-token",
            user_id=user.entity_id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    r = client.post("/api/v1/auth/login", json={"token": "expired-token"})
    assert r.status_code == 410

    db = SessionLocal()
    try:
        assert (
            db.query(LoginToken).filter(LoginToken.token == "expired-token").first() is None
        )
    finally:
        db.close()


def test_login_rejects_token_for_archived_user(client, admin_token, admin_headers):
    """Archive a user between minting and redeeming a token. The
    redeem path defensively 410s instead of issuing a JWT for a
    no-longer-current entity."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "ghost@local.dev", "name": "Ghost"},
    )
    assert r.status_code == 201

    from backend.database import SessionLocal
    from backend.models import LoginToken, User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current(db.query(User)).filter(User.email == "ghost@local.dev").first()
        assert user is not None
        uid = user.entity_id
        row = db.query(LoginToken).filter(LoginToken.user_id == uid).order_by(
            LoginToken.created_at.desc()
        ).first()
        assert row is not None
        raw = row.token
    finally:
        db.close()

    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    assert r.status_code == 204

    r = client.post("/api/v1/auth/login", json={"token": raw})
    assert r.status_code == 410


def test_restored_user_can_log_in_via_magic_link(client, admin_headers):
    """End-to-end restore round-trip: register → admin deletes →
    re-register (restores SCD2 chain) → mint link via
    /auth/login-link → redeem → fresh JWT against the restored
    entity_id."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "phoenix@local.dev", "name": "Phoenix"},
    )
    assert r.status_code == 201

    from backend.database import SessionLocal
    from backend.models import LoginToken, User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = (
            scd2.current(db.query(User)).filter(User.email == "phoenix@local.dev").first()
        )
        assert user is not None
        uid_before = user.entity_id
    finally:
        db.close()

    assert (
        client.delete(f"/api/v1/admin/users/{uid_before}", headers=admin_headers).status_code
        == 204
    )

    # Re-register: SCD2 chain restores, entity_id preserved.
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "phoenix@local.dev", "name": "Phoenix-back"},
    )
    assert r.status_code == 201

    # Independent /login-link to mint a fresh token (the register
    # path also mints one but we're proving the explicit re-login
    # round-trip works after restore).
    assert (
        client.post(
            "/api/v1/auth/login-link", json={"email": "phoenix@local.dev"}
        ).status_code
        == 200
    )

    db = SessionLocal()
    try:
        user = (
            scd2.current(db.query(User)).filter(User.email == "phoenix@local.dev").first()
        )
        assert user is not None
        assert user.entity_id == uid_before  # SCD2 chain restored
        # Pick the most recent token for this user, regardless of
        # which endpoint minted it.
        row = (
            db.query(LoginToken)
            .filter(LoginToken.user_id == user.entity_id)
            .order_by(LoginToken.created_at.desc())
            .first()
        )
        assert row is not None
        raw = row.token
    finally:
        db.close()

    r = client.post("/api/v1/auth/login", json={"token": raw})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == uid_before
    assert body["user"]["is_approved"] is False  # gate re-required after restore
