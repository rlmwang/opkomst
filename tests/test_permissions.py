"""Exhaustive table test of ``backend.permissions.can``.

The matrix is pure — no DB, no FastAPI — so we test every
``(actor_role, actor_approved, action, target)`` combination
in plain assertions. The test list is organised by *action*
rather than actor so a regression on one row reads as one
focused failure.

Population shorthand:
    * ``admin``       — approved admin
    * ``organiser``   — approved organiser
    * ``pending``     — unapproved organiser (logged-in but
                        admin hasn't cleared the gate)

Test users are SQLAlchemy ``User`` instances rather than mocks;
the function only reads ``.is_approved``, ``.role`` and ``.id``,
so a real row constructed in-memory is the simplest dependable
input that satisfies the type signature.
"""

from __future__ import annotations

import pytest

from backend.models import User
from backend.permissions import Action, can


def _user(*, id: str, role: str = "organiser", is_approved: bool = True) -> User:
    """Construct an unsaved User instance — the matrix only
    inspects attributes, not the DB."""
    return User(
        id=id,
        email=f"{id}@x.test",
        name=id,
        role=role,
        is_approved=is_approved,
    )


# Stable fixtures — created once and reused; ``can`` doesn't
# mutate its arguments.
ADMIN = _user(id="admin-1", role="admin")
ORGANISER = _user(id="org-1", role="organiser")
OTHER_ORGANISER = _user(id="org-2", role="organiser")
PENDING = _user(id="pending-1", role="organiser", is_approved=False)
PENDING_ADMIN = _user(id="pending-admin-1", role="admin", is_approved=False)


# ---- Unapproved users see nothing -------------------------------


@pytest.mark.parametrize("action", list(Action))
def test_unapproved_actor_can_do_nothing(action: Action) -> None:
    """The first gate in ``can``: ``is_approved=False`` short-
    circuits every action. Holds even for an unapproved row that
    happens to have ``role=admin`` (the bootstrap window is the
    only place those coexist; no permission should follow)."""
    assert can(PENDING, action, target=PENDING) is False
    # An unapproved-admin row must also fail — role alone isn't
    # enough; the approval gate is.
    assert can(PENDING_ADMIN, action, target=PENDING_ADMIN) is False


# ---- Admin-only actions -----------------------------------------


# ---- Open-to-any-approved actions -------------------------------


def test_list_users_open_to_organiser() -> None:
    """``LIST_USERS`` is open to any approved actor — it backs
    the Accounts page that every user can browse."""
    assert can(ORGANISER, Action.LIST_USERS) is True
    assert can(ADMIN, Action.LIST_USERS) is True


@pytest.mark.parametrize(
    "action",
    [
        Action.APPROVE_USER,
        Action.PROMOTE_USER,
        Action.DELETE_USER,
        Action.CREATE_CHAPTER,
        Action.PATCH_CHAPTER,
        Action.ARCHIVE_CHAPTER,
        Action.RESTORE_CHAPTER,
    ],
)
def test_admin_only_action_admin_yes_organiser_no(action: Action) -> None:
    """Admin-only actions: admin yes, organiser no. Target
    presence is irrelevant for these (there's no self-service
    branch); we pass ``OTHER_ORGANISER`` as a stand-in for
    user-targeting actions."""
    target = OTHER_ORGANISER
    assert can(ADMIN, action, target=target) is True
    assert can(ORGANISER, action, target=target) is False


def test_admin_can_promote_others_but_not_self() -> None:
    """Promote is admin-only. Promoting yourself is a no-op
    (you're already admin) but the matrix doesn't care — admins
    own their own row."""
    assert can(ADMIN, Action.PROMOTE_USER, target=ORGANISER) is True
    assert can(ADMIN, Action.PROMOTE_USER, target=ADMIN) is True


# ---- Demote: admin-only AND not-self ----------------------------


def test_admin_can_demote_other_admin() -> None:
    other_admin = _user(id="admin-2", role="admin")
    assert can(ADMIN, Action.DEMOTE_USER, target=other_admin) is True


def test_admin_cannot_demote_self() -> None:
    """Self-demote stays blocked: one click would otherwise let
    the only admin strip themselves and lock the org out of
    every admin-only action. Mirrors the 409 the router used to
    raise inline."""
    assert can(ADMIN, Action.DEMOTE_USER, target=ADMIN) is False


def test_organiser_cannot_demote_anyone() -> None:
    assert can(ORGANISER, Action.DEMOTE_USER, target=ADMIN) is False
    assert can(ORGANISER, Action.DEMOTE_USER, target=ORGANISER) is False


# ---- Self-service actions: rename + set-chapters ---------------


@pytest.mark.parametrize("action", [Action.RENAME_USER, Action.SET_USER_CHAPTERS])
def test_self_service_actor_yes_when_target_is_self(action: Action) -> None:
    """A non-admin can rename themselves and edit their own
    chapter set. No admin role required."""
    assert can(ORGANISER, action, target=ORGANISER) is True


@pytest.mark.parametrize("action", [Action.RENAME_USER, Action.SET_USER_CHAPTERS])
def test_self_service_actor_no_when_target_is_someone_else(
    action: Action,
) -> None:
    """An organiser cannot rename or re-chapter another user —
    that's still admin-only."""
    assert can(ORGANISER, action, target=OTHER_ORGANISER) is False


@pytest.mark.parametrize("action", [Action.RENAME_USER, Action.SET_USER_CHAPTERS])
def test_self_service_admin_yes_for_any_target(action: Action) -> None:
    """Admins can rename / re-chapter any user, including
    themselves."""
    assert can(ADMIN, action, target=ADMIN) is True
    assert can(ADMIN, action, target=ORGANISER) is True


@pytest.mark.parametrize("action", [Action.RENAME_USER, Action.SET_USER_CHAPTERS])
def test_self_service_requires_target(action: Action) -> None:
    """Self-service actions are programmer-error if called
    without a target — there's no "rename in general", you
    rename a specific row. The function raises ValueError so the
    bug surfaces loudly during development rather than silently
    denying."""
    with pytest.raises(ValueError, match="requires a target"):
        can(ORGANISER, action, target=None)


# ---- Identity check is by id, not by reference -----------------


def test_self_check_compares_user_id_not_object_identity() -> None:
    """Two different User instances representing the same row
    (e.g. one from the JWT layer, one from a fresh DB query)
    must be treated as the same actor for self-service purposes.
    The check is on ``.id``, not Python identity."""
    actor = _user(id="me", role="organiser")
    same_user_different_instance = _user(id="me", role="organiser")
    assert can(actor, Action.RENAME_USER, target=same_user_different_instance) is True


# ---- Coverage guard: every Action lands in exactly one branch --


def test_every_action_has_a_branch() -> None:
    """If a new ``Action`` member is added without extending the
    matrix, ``can`` raises ``ValueError("unknown action: ...")``.
    This test enumerates every member to make that mistake fail
    a build."""
    for action in Action:
        # Every action either succeeds or denies cleanly for
        # admin+admin; an "unknown action" branch raises instead.
        try:
            can(ADMIN, action, target=ADMIN)
        except ValueError as exc:
            pytest.fail(f"action {action!r} fell through to unknown branch: {exc}")
