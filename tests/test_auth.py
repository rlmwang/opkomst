"""Auth flow: register → bootstrap admin auto-approve, register a
non-bootstrap user → unverified state, login, JWT survives user
edits, soft-delete + restore via re-register."""


def test_bootstrap_admin_auto_approves(client, admin_token):
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "admin@local.dev"
    assert me["role"] == "admin"
    assert me["is_approved"] is True
    assert me["email_verified_at"] is not None


def test_login_requires_correct_password(client, admin_token):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "wrong"},
    )
    assert r.status_code == 401


def test_login_returns_jwt(client, admin_token):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "admin1234"},
    )
    assert r.status_code == 200
    assert r.json()["token"]


def test_jwt_id_stable_across_user_updates(client, admin_headers, chapter_id):
    """JWT signs ``entity_id``, so it must keep working when the
    user's row id changes (i.e. after any SCD2 update)."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "x@local.dev", "password": "pw12345678", "name": "X"},
    )
    uid = r.json()["user"]["id"]
    token = r.json()["token"]
    # Promote-via-approve causes an SCD2 update — row id changes.
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
        json={"email": "rejoin@local.dev", "password": "pw12345678", "name": "Re"},
    )
    uid = r.json()["user"]["id"]
    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    assert r.status_code == 204
    # Reregister with same email — should restore.
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "rejoin@local.dev", "password": "newpw87654", "name": "Re-back"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["id"] == uid  # entity_id preserved
    assert body["user"]["is_approved"] is False  # gates re-required


def test_explicit_validation_for_register(client):
    # Email format
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "pw12345678", "name": "X"},
    )
    assert r.status_code == 422


def test_register_rate_limit(client):
    """5/hour on register — sixth from the same IP gets 429."""
    for i in range(5):
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"rl{i}@local.dev",
                "password": "pw12345678",
                "name": "RL",
            },
        )
        assert r.status_code in (201, 422), r.text
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "rl-over@local.dev", "password": "pw12345678", "name": "RL"},
    )
    assert r.status_code == 429
