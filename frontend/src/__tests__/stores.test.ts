/**
 * The session, and the questions the app asks it.
 *
 * Every gate in the app reads one of these: whether somebody is signed
 * in, approved, an admin, or on a paid plan. The store is exercised
 * against a mocked API client, so an
 * accidental network call fails loudly rather than quietly returning
 * undefined.
 *
 * The store is module state, and a test file shares one module
 * registry, so each test imports it fresh.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@/api/client";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

const mockGet = vi.mocked(apiClient.get);

const BASE = {
  id: "u1",
  email: "x@y",
  name: "X",
  role: "organiser" as const,
  is_approved: false,
  chapters: [],
  created_at: "2026-01-01T00:00:00Z",
  tenant_kind: "organisation",
  participant_cap: null,
  participant_mail: true,
};

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

/** A fresh store, signed in as this user. The only way a user gets in
 *  is the way the app does it: a token, and ``/auth/me``. */
async function signedInAs(user: Record<string, unknown>) {
  const store = await import("@/stores/auth.svelte");
  vi.mocked(apiClient.getToken).mockReturnValue("tok");
  mockGet.mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user;
    throw new Error(`unexpected GET ${path}`);
  });
  await store.fetchMe();
  return store;
}

describe("the session", () => {
  it("starts signed out and unloaded, and every gate is shut", async () => {
    const { auth } = await import("@/stores/auth.svelte");
    expect(auth.user).toBeNull();
    expect(auth.loaded).toBe(false);
    expect(auth.isAuthenticated).toBe(false);
    expect(auth.isApproved).toBe(false);
    expect(auth.isAdmin).toBe(false);
  });

  it("opens the gates the account's own row opens", async () => {
    // Signed in but not approved yet.
    let store = await signedInAs({ ...BASE });
    expect(store.auth.isAuthenticated).toBe(true);
    expect(store.auth.isApproved).toBe(false);
    expect(store.auth.isAdmin).toBe(false);

    vi.resetModules();
    store = await signedInAs({ ...BASE, is_approved: true });
    expect(store.auth.isApproved).toBe(true);
    expect(store.auth.isAdmin).toBe(false);

    vi.resetModules();
    store = await signedInAs({ ...BASE, role: "admin", is_approved: true });
    expect(store.auth.isAdmin).toBe(true);

    // An admin who is not approved is not an admin, which is what the
    // server says too.
    vi.resetModules();
    store = await signedInAs({ ...BASE, role: "admin", is_approved: false });
    expect(store.auth.isAdmin).toBe(false);
  });

  it("participantMail is false signed out, and follows the account signed in", async () => {
    // What the event and roster forms read to decide whether the
    // reminder and questionnaire controls exist at all. Signed out is
    // the start door, whose account will be a free one.
    const { auth } = await import("@/stores/auth.svelte");
    expect(auth.participantMail).toBe(false);

    vi.resetModules();
    let store = await signedInAs({ ...BASE, tenant_kind: "personal", participant_mail: false });
    expect(store.auth.participantMail).toBe(false);

    vi.resetModules();
    store = await signedInAs({ ...BASE, tenant_kind: "personal", participant_mail: true });
    expect(store.auth.participantMail).toBe(true);
  });

  it("reads the user row in one request", async () => {
    const store = await signedInAs({ ...BASE, role: "admin", is_approved: true });
    expect(store.auth.isAdmin).toBe(true);
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("clears the session on logout", async () => {
    const store = await signedInAs({ ...BASE, role: "admin", is_approved: true });
    expect(store.auth.isAuthenticated).toBe(true);

    store.logout();
    expect(store.auth.user).toBeNull();
    expect(store.auth.isAuthenticated).toBe(false);
    expect(store.auth.isAdmin).toBe(false);
  });
});
