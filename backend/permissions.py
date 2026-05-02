"""The access matrix as a pure function.

Every router-side authorization check resolves to one call:
``permissions.can(actor, action, target=None)``. The function
takes only the typed inputs needed to decide — no DB session,
no request, no env — so the entire matrix is exhaustively
table-testable in milliseconds (``tests/test_permissions.py``).

Two populations exist beyond approved/admin: an unapproved
user can do nothing on this surface (the JWT is valid but the
admin gate hasn't cleared), and a soft-deleted user has no
JWT at all (``get_current_user`` rejects on ``deleted_at IS NOT
NULL``), so neither needs an explicit branch in this matrix.

The pattern: most actions are admin-only; the *self-service*
actions (rename, set chapters) carve out an additional
"actor is the target" branch. Privilege-elevating actions
(promote, demote, delete) deliberately have no self-service
branch — a user cannot grant themselves admin, demote
themselves out of admin (mirrors the existing 409
self-demotion rule), or delete their own account.

Read endpoints are open to every approved user: the chapter
list, the user list, /me. There is no "see only your own row"
mode — peers seeing each other is consistent with the
project's organising mission and matches how the dashboard
treats events (every approved user sees every event in their
chapter set).
"""

from enum import StrEnum

from .models import User


class Action(StrEnum):
    """Every distinct authz decision the routers make. Adding a
    new endpoint adds a member here and a branch in ``can``;
    keep these two in lock-step."""

    # User reads / writes
    LIST_USERS = "list_users"
    APPROVE_USER = "approve_user"
    RENAME_USER = "rename_user"
    SET_USER_CHAPTERS = "set_user_chapters"
    PROMOTE_USER = "promote_user"
    DEMOTE_USER = "demote_user"
    DELETE_USER = "delete_user"

    # Chapter reads / writes
    CREATE_CHAPTER = "create_chapter"
    PATCH_CHAPTER = "patch_chapter"
    ARCHIVE_CHAPTER = "archive_chapter"
    RESTORE_CHAPTER = "restore_chapter"


# Admin-only actions: pure role gate, no self-service branch.
_ADMIN_ONLY: frozenset[Action] = frozenset(
    {
        Action.APPROVE_USER,
        Action.PROMOTE_USER,
        Action.DELETE_USER,
        Action.CREATE_CHAPTER,
        Action.PATCH_CHAPTER,
        Action.ARCHIVE_CHAPTER,
        Action.RESTORE_CHAPTER,
    }
)

# Open to every approved actor — reads + the open-to-all
# accounts page surface. The matrix still funnels these through
# ``can`` so the gate is consistent and unauthenticated /
# unapproved actors are blocked uniformly upstream.
_ANY_APPROVED: frozenset[Action] = frozenset({Action.LIST_USERS})

# Self-service actions: admin OR ``target == actor``. The
# target field is required for these — passing ``None`` for a
# self-service action is a programming error.
_SELF_OR_ADMIN: frozenset[Action] = frozenset({Action.RENAME_USER, Action.SET_USER_CHAPTERS})


def can(actor: User, action: Action, target: User | None = None) -> bool:
    """Return True iff ``actor`` is allowed to perform ``action``.

    For user-targeting actions, ``target`` is the affected user
    row; for chapter-targeting actions ``target`` is unused
    (the chapter id is validated separately, where needed, by
    the calling router).

    Unapproved actors are blocked uniformly. Admin-only actions
    additionally require ``actor.role == "admin"``. Demote
    carries an extra anti-foot-shoot rule: an admin cannot
    demote themselves (would let one click strip the org of
    its only admin)."""
    if not actor.is_approved:
        return False

    is_admin = actor.role == "admin"
    is_self = target is not None and target.id == actor.id

    if action in _ANY_APPROVED:
        # Already gated by ``actor.is_approved`` above.
        return True

    if action == Action.DEMOTE_USER:
        # Admin-only AND not self — preserved from the previous
        # router rule, encoded here so every caller sees the
        # same answer.
        return is_admin and not is_self

    if action in _ADMIN_ONLY:
        return is_admin

    if action in _SELF_OR_ADMIN:
        if target is None:
            raise ValueError(f"{action} requires a target user; got None")
        return is_admin or is_self

    # Should be unreachable as long as every Action member is
    # covered by exactly one branch above. Raising rather than
    # returning False so a missing-branch bug surfaces as a 500
    # rather than a silent permission deny.
    raise ValueError(f"unknown action: {action!r}")
