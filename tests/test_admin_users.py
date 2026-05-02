"""Coverage for ``backend/routers/admin.py``.

The admin user-management endpoints (approve / promote / demote /
assign-chapter / delete) are the load-bearing surface for the
SCD2-removal refactor — every one of them currently calls
``scd2.scd2_update`` and after R2 they become plain UPDATEs.
Pinning the user-visible behaviour here means the refactor is
constrained to behaviour-preserving changes.
"""

from __future__ import annotations

from typing import Any

from backend.auth import create_token
from backend.database import SessionLocal
from backend.models import User
from tests._helpers.users import register_user


def _register(client: Any, email: str, name: str = "X") -> str:
    return register_user(client, email, name)


def _approve(client, headers, uid: str, *chapter_ids: str):  # noqa: ANN001
    """Approve a user with one or more chapter memberships.
    Variadic so single-chapter callers still read naturally."""
    return client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=headers,
        json={"chapter_ids": list(chapter_ids)},
    )


# --- list ----------------------------------------------------------


def test_list_users_returns_admin_plus_pending(client, admin_headers, chapter_id):
    """The admin who registered is approved by bootstrap; a freshly
    registered user shows up unapproved."""
    _register(client, "newbie@local.dev", "New")
    r = client.get("/api/v1/admin/users", headers=admin_headers)
    assert r.status_code == 200
    by_email = {u["email"]: u for u in r.json()}
    assert by_email["admin@local.dev"]["is_approved"] is True
    assert by_email["admin@local.dev"]["role"] == "admin"
    assert by_email["newbie@local.dev"]["is_approved"] is False


def test_list_users_pending_filter(client, admin_headers, chapter_id):
    _register(client, "newbie@local.dev")
    r = client.get("/api/v1/admin/users?pending=true", headers=admin_headers)
    assert r.status_code == 200
    rows = r.json()
    assert all(u["is_approved"] is False for u in rows)
    emails = {u["email"] for u in rows}
    assert "newbie@local.dev" in emails
    assert "admin@local.dev" not in emails


def test_list_users_requires_authentication(client):
    """List-users is open to every approved user (organisers see
    each other in the accounts page) but still rejects an
    anonymous request — the JWT gate is upstream of the matrix."""
    r = client.get("/api/v1/admin/users")
    assert r.status_code == 401


def test_pending_count_admin_only(client, admin_headers, organiser_token):
    """The pending-count endpoint backs an admin-only navbar
    indicator; surfacing it to organisers would just be noise.
    Organisers get 403."""
    r = client.get("/api/v1/admin/users/pending-count", headers=admin_headers)
    assert r.status_code == 200
    assert "count" in r.json()

    r = client.get(
        "/api/v1/admin/users/pending-count",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


def test_pending_count_reflects_unapproved_user_changes(client, admin_headers, chapter_id):
    """Count is the number of live users with ``is_approved =
    False``. Approving a pending user drops the count by one."""
    base = client.get("/api/v1/admin/users/pending-count", headers=admin_headers).json()["count"]

    uid = _register(client, "pendcount@local.dev", "Pending Counter")
    after_register = client.get("/api/v1/admin/users/pending-count", headers=admin_headers).json()["count"]
    assert after_register == base + 1

    _approve(client, admin_headers, uid, chapter_id)
    after_approve = client.get("/api/v1/admin/users/pending-count", headers=admin_headers).json()["count"]
    assert after_approve == base


def test_list_users_open_to_organiser(client, organiser_headers):
    """``permissions.LIST_USERS`` admits any approved actor.
    Organisers can see the full list — the page is now Accounts,
    not Admin."""
    r = client.get("/api/v1/admin/users", headers=organiser_headers)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert "admin@local.dev" in emails
    assert "organiser@local.dev" in emails


# --- approve -------------------------------------------------------


def test_approve_user_happy_path(client, admin_headers, chapter_id, fake_email):
    fake_email.reset()
    uid = _register(client, "approve.me@local.dev", "Approve Me")
    r = _approve(client, admin_headers, uid, chapter_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == uid
    assert body["is_approved"] is True
    assert [c["id"] for c in body["chapters"]] == [chapter_id]
    assert [c["name"] for c in body["chapters"]] == ["Amsterdam"]

    # Approval email queued. The fake backend captures (to,
    # subject, html, ...) — there's no ``template_name`` on
    # ``CapturedEmail``, so we sniff the subject line instead.
    captured = fake_email.to("approve.me@local.dev")
    assert any("goedgekeurd" in c.subject.lower() for c in captured)


def test_approve_user_with_multiple_chapters(client, admin_headers, chapter_id):
    """Multi-chapter approval lands every membership in one call.
    The ``chapters`` array on the response carries them sorted by
    name (Amsterdam < Utrecht alphabetically)."""
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    utrecht = r2.json()["id"]

    uid = _register(client, "multi.approve@local.dev")
    r = _approve(client, admin_headers, uid, chapter_id, utrecht)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {c["name"] for c in body["chapters"]} == {"Amsterdam", "Utrecht"}
    # Sorted: stable UI rendering doesn't depend on insertion order.
    assert [c["name"] for c in body["chapters"]] == ["Amsterdam", "Utrecht"]


def test_approve_with_empty_chapter_list_is_allowed(client, admin_headers, fake_email):
    """An admin can approve without picking chapters — the user
    self-picks via the dashboard's onboarding banner. The
    approval email's empty-set branch gives a "pick chapters
    inside the app" message instead of a chapter list."""
    fake_email.reset()
    uid = _register(client, "self.pick@local.dev", "Self Picker")
    r = client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={"chapter_ids": []},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_approved"] is True
    assert body["chapters"] == []

    captured = fake_email.to("self.pick@local.dev")
    assert any("goedgekeurd" in c.subject.lower() for c in captured)


def test_approve_without_chapter_ids_field_is_allowed(client, admin_headers):
    """Body without the field at all also works — the schema's
    ``default_factory=list`` fills it in."""
    uid = _register(client, "no.field@local.dev")
    r = client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 200, r.text


def test_approve_with_archived_chapter_returns_400(client, admin_headers, chapter_id, admin_token):
    """An archived chapter is invalid for fresh approvals — the
    UI's MultiSelect already excludes it, but the server rejects
    too as defence in depth."""
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Archived"})
    arch = r2.json()["id"]
    client.delete(f"/api/v1/chapters/{arch}", headers=admin_headers)

    uid = _register(client, "x@local.dev")
    r = _approve(client, admin_headers, uid, chapter_id, arch)
    assert r.status_code == 400


def test_approve_already_approved_returns_409(client, admin_headers, chapter_id):
    uid = _register(client, "x@local.dev")
    assert _approve(client, admin_headers, uid, chapter_id).status_code == 200
    r = _approve(client, admin_headers, uid, chapter_id)
    assert r.status_code == 409


def test_approve_with_unknown_chapter_returns_400(client, admin_headers):
    uid = _register(client, "x@local.dev")
    r = _approve(client, admin_headers, uid, "no-such-chapter")
    assert r.status_code == 400


def test_approve_unknown_user_returns_404(client, admin_headers, chapter_id):
    r = _approve(client, admin_headers, "no-such-user", chapter_id)
    assert r.status_code == 404


def test_approve_requires_admin(client, organiser_token, chapter_id):
    uid = _register(client, "newbie@local.dev")
    r = client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"chapter_ids": [chapter_id]},
    )
    assert r.status_code == 403


# --- set-chapters --------------------------------------------------


def test_set_chapters_replaces_membership_set(client, admin_headers, chapter_id):
    """``/set-chapters`` is a full-set replace, not an add. Pass a
    list, the row converges to that exact set."""
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    utrecht = r2.json()["id"]
    r3 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Den Haag"})
    den_haag = r3.json()["id"]

    uid = _register(client, "moveme@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    # User is in {Amsterdam}.

    # Replace with {Utrecht, Den Haag} — Amsterdam removed in
    # the same call.
    r = client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers=admin_headers,
        json={"chapter_ids": [utrecht, den_haag]},
    )
    assert r.status_code == 200
    body = r.json()
    assert {c["name"] for c in body["chapters"]} == {"Utrecht", "Den Haag"}


def test_set_chapters_idempotent_on_repeated_call(client, admin_headers, chapter_id):
    """Calling /set-chapters with the same list twice converges
    on the same state — no PK violation, no spurious diff."""
    uid = _register(client, "stable@local.dev")
    _approve(client, admin_headers, uid, chapter_id)

    payload = {"chapter_ids": [chapter_id]}
    r1 = client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers=admin_headers,
        json=payload,
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers=admin_headers,
        json=payload,
    )
    assert r2.status_code == 200
    assert [c["id"] for c in r2.json()["chapters"]] == [chapter_id]


def test_set_chapters_empty_returns_422(client, admin_headers, chapter_id):
    uid = _register(client, "naked@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    r = client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers=admin_headers,
        json={"chapter_ids": []},
    )
    assert r.status_code == 422


def test_set_chapters_unknown_chapter_returns_400(client, admin_headers, chapter_id):
    uid = _register(client, "x@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    r = client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers=admin_headers,
        json={"chapter_ids": ["no-such-chapter"]},
    )
    assert r.status_code == 400


# --- rename --------------------------------------------------------


def test_rename_user_happy_path(client, admin_headers):
    uid = _register(client, "rename.me@local.dev", "Old Name")
    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": "New Name"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == uid
    assert body["name"] == "New Name"

    # Persisted across a fresh GET — guards against returning the
    # mutated DTO without committing the row.
    r = client.get("/api/v1/admin/users", headers=admin_headers)
    by_id = {u["id"]: u for u in r.json()}
    assert by_id[uid]["name"] == "New Name"


def test_rename_user_strips_whitespace(client, admin_headers):
    """Pydantic's ``min_length`` doesn't strip; the handler does.
    A name with leading/trailing whitespace is stored trimmed."""
    uid = _register(client, "trim@local.dev", "Old")
    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": "   Padded   "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Padded"


def test_rename_user_blank_rejected(client, admin_headers):
    """Empty string fails Pydantic min_length=1; whitespace-only
    fails the handler's strip-then-check. Both must 422 before the
    row is touched."""
    uid = _register(client, "blank@local.dev", "Original")

    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": ""},
    )
    assert r.status_code == 422

    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": "   "},
    )
    assert r.status_code == 422

    # Row still has the original name.
    r = client.get("/api/v1/admin/users", headers=admin_headers)
    by_id = {u["id"]: u for u in r.json()}
    assert by_id[uid]["name"] == "Original"


def test_rename_unknown_user_returns_404(client, admin_headers):
    r = client.post(
        "/api/v1/admin/users/nonexistent-id/rename",
        headers=admin_headers,
        json={"name": "Phantom"},
    )
    assert r.status_code == 404


def test_rename_soft_deleted_user_returns_404(client, admin_headers):
    """``_get_live_user_or_404`` filters on deleted_at IS NULL —
    a soft-deleted user is not a valid rename target."""
    uid = _register(client, "ghost@local.dev", "Ghost")
    assert client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers).status_code == 204
    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": "Resurrected"},
    )
    assert r.status_code == 404


def test_rename_self_allowed(client, admin_headers, admin_token):
    """Unlike demote/delete, self-rename is fine — no way to lock
    yourself out by changing your own display name."""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@local.dev", User.deleted_at.is_(None)).first()
        assert admin is not None
        uid = admin.id
    finally:
        db.close()

    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": "Renamed Admin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Admin"


def test_rename_self_allowed_for_organiser(client, organiser_token):
    """Self-service: an organiser can rename their own row
    without admin involvement. The matrix carves out the
    admin-OR-self branch on RENAME_USER."""
    db = SessionLocal()
    try:
        organiser = db.query(User).filter(User.email == "organiser@local.dev", User.deleted_at.is_(None)).first()
        assert organiser is not None
        uid = organiser.id
    finally:
        db.close()

    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"name": "Self-renamed"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Self-renamed"


def test_rename_other_user_requires_admin(client, admin_headers, organiser_token):
    """The self-service carve-out is *only* for the actor's own
    row. Renaming someone else is still admin-only."""
    # Make a third user the organiser will try to rename.
    other_uid = _register(client, "victim@local.dev", "Victim")

    r = client.post(
        f"/api/v1/admin/users/{other_uid}/rename",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"name": "Sneaky"},
    )
    assert r.status_code == 403


# --- self-service set-chapters --------------------------------


def test_set_own_chapters_allowed_for_organiser(client, admin_headers, organiser_token, chapter_id):
    """Self-service: an organiser can change their own chapter
    membership without admin involvement. Mirrors the
    admin-OR-self branch on SET_USER_CHAPTERS."""
    # Add a second chapter to choose from.
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    utrecht = r.json()["id"]

    db = SessionLocal()
    try:
        organiser = db.query(User).filter(User.email == "organiser@local.dev", User.deleted_at.is_(None)).first()
        assert organiser is not None
        uid = organiser.id
    finally:
        db.close()

    r = client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"chapter_ids": [chapter_id, utrecht]},
    )
    assert r.status_code == 200
    assert {c["name"] for c in r.json()["chapters"]} == {"Amsterdam", "Utrecht"}


def test_set_other_users_chapters_requires_admin(client, organiser_token, chapter_id):
    """An organiser can't reach into another user's chapter set —
    the self-service carve-out is only for their own row."""
    other_uid = _register(client, "other@local.dev")
    r = client.post(
        f"/api/v1/admin/users/{other_uid}/set-chapters",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"chapter_ids": [chapter_id]},
    )
    assert r.status_code == 403


# --- privilege-elevating actions remain admin-only -------------


def test_organiser_cannot_promote_self(client, organiser_token):
    """Privilege-escalation guard: an organiser submitting a
    promote against their own id must 403, not 200. The matrix
    has no self-service carve-out for PROMOTE_USER."""
    db = SessionLocal()
    try:
        organiser = db.query(User).filter(User.email == "organiser@local.dev", User.deleted_at.is_(None)).first()
        assert organiser is not None
        uid = organiser.id
    finally:
        db.close()
    r = client.post(
        f"/api/v1/admin/users/{uid}/promote",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403

    # And the row didn't get bumped despite the failed call.
    db = SessionLocal()
    try:
        organiser = db.query(User).filter(User.id == uid).first()
        assert organiser is not None
        assert organiser.role == "organiser"
    finally:
        db.close()


def test_organiser_cannot_promote_others(client, admin_headers, organiser_token, chapter_id):
    other_uid = _register(client, "promote.target@local.dev")
    _approve(client, admin_headers, other_uid, chapter_id)
    r = client.post(
        f"/api/v1/admin/users/{other_uid}/promote",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


def test_organiser_cannot_demote_anyone(client, admin_headers, organiser_token, chapter_id):
    """Demote is admin-only AND not-self. An organiser shouldn't
    even be able to attempt it on an existing admin."""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@local.dev", User.deleted_at.is_(None)).first()
        assert admin is not None
        admin_uid = admin.id
    finally:
        db.close()
    r = client.post(
        f"/api/v1/admin/users/{admin_uid}/demote",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


def test_organiser_cannot_delete_anyone(client, admin_headers, organiser_token):
    """Delete is admin-only — organisers cannot soft-delete
    themselves or anyone else."""
    other_uid = _register(client, "deletable@local.dev")
    r = client.delete(
        f"/api/v1/admin/users/{other_uid}",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403

    db = SessionLocal()
    try:
        organiser = db.query(User).filter(User.email == "organiser@local.dev", User.deleted_at.is_(None)).first()
        assert organiser is not None
        own_uid = organiser.id
    finally:
        db.close()
    r = client.delete(
        f"/api/v1/admin/users/{own_uid}",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


# --- chapter mutations remain admin-only -----------------------


def test_organiser_cannot_create_chapter(client, organiser_token):
    """Chapter mutations are admin-only by the matrix; this
    test pins the router-level enforcement."""
    r = client.post(
        "/api/v1/chapters",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"name": "Rogue chapter"},
    )
    assert r.status_code == 403


def test_organiser_cannot_archive_chapter(client, admin_headers, organiser_token, chapter_id):
    r = client.delete(
        f"/api/v1/chapters/{chapter_id}",
        headers={"Authorization": f"Bearer {organiser_token}"},
    )
    assert r.status_code == 403


def test_rename_unauthenticated_rejected(client):
    r = client.post(
        "/api/v1/admin/users/any-id/rename",
        json={"name": "Hopeful"},
    )
    assert r.status_code == 401


def test_rename_log_extras_carry_length_not_value(client, admin_headers, monkeypatch):
    """Privacy invariant: the ``user_renamed`` audit line records
    ``new_name_len`` (forensic value, no PII) rather than the
    user-supplied string. Structlog has its own pipeline so we
    spy on the call directly rather than going via caplog."""
    import backend.routers.admin as admin_module

    captured: list[tuple[str, dict]] = []
    real_logger = admin_module.logger

    class _Spy:
        def info(self, event: str, **kw):  # noqa: ANN001
            captured.append((event, kw))
            return real_logger.info(event, **kw)

    monkeypatch.setattr(admin_module, "logger", _Spy())

    uid = _register(client, "logged@local.dev", "Before")
    r = client.post(
        f"/api/v1/admin/users/{uid}/rename",
        headers=admin_headers,
        json={"name": "Sensitive Name"},
    )
    assert r.status_code == 200

    rename_calls = [(e, kw) for e, kw in captured if e == "user_renamed"]
    assert len(rename_calls) == 1
    _, kw = rename_calls[0]
    assert kw["new_name_len"] == len("Sensitive Name")
    assert "new_name" not in kw  # the value itself never travels with the log


# --- promote / demote ----------------------------------------------


def test_promote_user_happy_path(client, admin_headers, chapter_id):
    uid = _register(client, "promo@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    r = client.post(f"/api/v1/admin/users/{uid}/promote", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_promote_already_admin_returns_409(client, admin_headers, chapter_id):
    uid = _register(client, "promo@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    client.post(f"/api/v1/admin/users/{uid}/promote", headers=admin_headers)
    r = client.post(f"/api/v1/admin/users/{uid}/promote", headers=admin_headers)
    assert r.status_code == 409


def test_promote_unapproved_user_returns_409(client, admin_headers):
    """Promote-before-approve is a no-op pattern: an admin must first
    approve the user (which assigns a chapter) before they can be
    promoted to admin themselves."""
    uid = _register(client, "promo@local.dev")
    r = client.post(f"/api/v1/admin/users/{uid}/promote", headers=admin_headers)
    assert r.status_code == 409


def test_demote_user_happy_path(client, admin_headers, chapter_id):
    uid = _register(client, "demo@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    client.post(f"/api/v1/admin/users/{uid}/promote", headers=admin_headers)
    r = client.post(f"/api/v1/admin/users/{uid}/demote", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "organiser"


def test_demote_self_blocked(client, admin_headers, admin_token):
    """The bootstrap admin can't demote themselves to organiser via
    one click — the org could end up with zero admins. The matrix
    encodes this as a uniform 403 alongside every other authz
    denial; the router doesn't have a special-case 409 for it
    anymore (one source of truth for permission decisions)."""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.deleted_at.is_(None)).filter(User.email == "admin@local.dev").first()
        assert admin is not None
        admin_id = admin.id
    finally:
        db.close()
    r = client.post(f"/api/v1/admin/users/{admin_id}/demote", headers=admin_headers)
    assert r.status_code == 403


def test_demote_non_admin_returns_409(client, admin_headers, chapter_id):
    uid = _register(client, "x@local.dev")
    _approve(client, admin_headers, uid, chapter_id)
    r = client.post(f"/api/v1/admin/users/{uid}/demote", headers=admin_headers)
    assert r.status_code == 409


# --- delete --------------------------------------------------------


def test_delete_user_soft_deletes(client, admin_headers, chapter_id):
    """Soft-delete closes the SCD2 chain; the email frees up."""
    uid = _register(client, "doomed@local.dev")
    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    assert r.status_code == 204

    # Re-registering the same email succeeds (restore branch).
    _register(client, "doomed@local.dev", "Reborn")

    # The restored row carries the same entity_id as before.
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.deleted_at.is_(None)).filter(User.email == "doomed@local.dev").first()
        assert user is not None
        assert user.id == uid
        assert user.is_approved is False
        assert user.role == "organiser"
    finally:
        db.close()


def test_delete_self_blocked(client, admin_headers, admin_token):
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.deleted_at.is_(None)).filter(User.email == "admin@local.dev").first()
        assert admin is not None
        admin_id = admin.id
    finally:
        db.close()
    r = client.delete(f"/api/v1/admin/users/{admin_id}", headers=admin_headers)
    assert r.status_code == 409


def test_jwt_for_deleted_user_invalidates(client, admin_headers, chapter_id):
    """A previously valid JWT becomes worthless the moment the user
    is soft-deleted — the SCD2 current_by_entity lookup returns
    None."""
    uid = _register(client, "ephemeral@local.dev")
    token = create_token(uid)
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 200
    )
    client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
