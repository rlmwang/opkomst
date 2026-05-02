/**
 * TypeScript port of ``backend/permissions.py::can``.
 *
 * The same matrix backs UI affordances on the Users page —
 * we hide / disable buttons the user can't actually invoke so
 * the frontend doesn't bait them into a 403. The backend is
 * still the authoritative gate; this file mirrors the rules
 * so the two stay in lock-step. Add a member here when you
 * add one to ``backend/permissions.py::Action``.
 */

import type { User } from "@/api/types";

export type Action =
  // User reads / writes
  | "list_users"
  | "approve_user"
  | "rename_user"
  | "set_user_chapters"
  | "promote_user"
  | "demote_user"
  | "delete_user"
  // Chapter reads / writes
  | "create_chapter"
  | "patch_chapter"
  | "archive_chapter"
  | "restore_chapter";

const ADMIN_ONLY = new Set<Action>([
  "approve_user",
  "promote_user",
  "delete_user",
  "create_chapter",
  "patch_chapter",
  "archive_chapter",
  "restore_chapter",
]);

const SELF_OR_ADMIN = new Set<Action>(["rename_user", "set_user_chapters"]);

const ANY_APPROVED = new Set<Action>(["list_users"]);

export function can(actor: User | null, action: Action, target?: User | null): boolean {
  if (!actor || !actor.is_approved) return false;

  const isAdmin = actor.role === "admin";
  const isSelf = target != null && target.id === actor.id;

  if (ANY_APPROVED.has(action)) return true;

  if (action === "demote_user") {
    // Admin-only AND not self — no-self-demote rule.
    return isAdmin && !isSelf;
  }
  if (ADMIN_ONLY.has(action)) return isAdmin;
  if (SELF_OR_ADMIN.has(action)) {
    if (target == null) {
      // Programmer error: self-service actions need a target.
      // Throwing in dev surfaces the bug; in prod the function
      // would have returned ``false`` either way and the user
      // sees no affordance.
      throw new Error(`${action} requires a target`);
    }
    return isAdmin || isSelf;
  }
  // Unreachable while every Action is enumerated above.
  throw new Error(`unknown action: ${action}`);
}
