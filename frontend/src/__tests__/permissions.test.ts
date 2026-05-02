/**
 * Mirror of ``tests/test_permissions.py`` for the TS port. Both
 * files describe the same matrix and must stay in lock-step;
 * the frontend mirror exists only to drive UI affordances, but
 * a divergence between the two would have a user click a button
 * that 403s every time. Easier to keep them parallel.
 */

import { describe, expect, it } from "vitest";
import { can, type Action } from "@/lib/permissions";
import type { User } from "@/api/types";

function user(over: Partial<User> = {}): User {
  return {
    id: "u",
    email: "u@x.test",
    name: "U",
    role: "organiser",
    is_approved: true,
    chapters: [],
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

const ADMIN = user({ id: "admin-1", role: "admin" });
const ORGANISER = user({ id: "org-1", role: "organiser" });
const OTHER = user({ id: "org-2", role: "organiser" });
const PENDING = user({ id: "pending", is_approved: false });

const ALL_ACTIONS: Action[] = [
  "list_users",
  "approve_user",
  "rename_user",
  "set_user_chapters",
  "promote_user",
  "demote_user",
  "delete_user",
  "create_chapter",
  "patch_chapter",
  "archive_chapter",
  "restore_chapter",
];

describe("permissions.can", () => {
  it.each(ALL_ACTIONS)("denies unapproved actor (%s)", (action) => {
    expect(can(PENDING, action, PENDING)).toBe(false);
  });

  it("denies an unauthenticated actor uniformly", () => {
    expect(can(null, "list_users")).toBe(false);
  });

  it("opens list_users to any approved actor", () => {
    expect(can(ORGANISER, "list_users")).toBe(true);
    expect(can(ADMIN, "list_users")).toBe(true);
  });

  it.each([
    "approve_user",
    "promote_user",
    "delete_user",
    "create_chapter",
    "patch_chapter",
    "archive_chapter",
    "restore_chapter",
  ] as const)("admin-only: %s", (action) => {
    expect(can(ADMIN, action, OTHER)).toBe(true);
    expect(can(ORGANISER, action, OTHER)).toBe(false);
  });

  it("self-rename: organiser yes, other no", () => {
    expect(can(ORGANISER, "rename_user", ORGANISER)).toBe(true);
    expect(can(ORGANISER, "rename_user", OTHER)).toBe(false);
  });

  it("self-set-chapters: organiser yes, other no", () => {
    expect(can(ORGANISER, "set_user_chapters", ORGANISER)).toBe(true);
    expect(can(ORGANISER, "set_user_chapters", OTHER)).toBe(false);
  });

  it("admin can rename / re-chapter anyone", () => {
    expect(can(ADMIN, "rename_user", ORGANISER)).toBe(true);
    expect(can(ADMIN, "set_user_chapters", ORGANISER)).toBe(true);
  });

  it("demote: admin can demote others but not self", () => {
    const otherAdmin = user({ id: "admin-2", role: "admin" });
    expect(can(ADMIN, "demote_user", otherAdmin)).toBe(true);
    expect(can(ADMIN, "demote_user", ADMIN)).toBe(false);
  });

  it("self-service requires a target — throws on null", () => {
    expect(() => can(ORGANISER, "rename_user", null)).toThrowError(/target/);
  });

  it("self check is by id, not object identity", () => {
    const sameRowDifferentInstance = user({ id: ORGANISER.id });
    expect(can(ORGANISER, "rename_user", sameRowDifferentInstance)).toBe(true);
  });
});
