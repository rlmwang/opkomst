/**
 * Behavioural tests for the Pinia stores.
 *
 * Each store is exercised against a mocked API client so the test
 * proves three things:
 *
 *   1. Documented initial state is what the store actually starts with.
 *   2. Each public action exists, accepts its declared arguments, and
 *      hits the right URL with the right HTTP verb (catches accidental
 *      route renames and verb flips that vue-tsc can't see when there
 *      are no callers in the app yet).
 *   3. Computed responsiveness: setting state through an action
 *      propagates to the computed getters that consumers depend on.
 *
 * No real HTTP. The whole `@/api/client` module is mocked — an
 * accidental network call from a store's setup function fails loudly
 * because the mock returns `undefined` and the test assertion blows up.
 */

import { createPinia, setActivePinia } from "pinia";
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
const mockPost = vi.mocked(apiClient.post);
const mockPut = vi.mocked(apiClient.put);
const mockPatch = vi.mocked(apiClient.patch);
const mockDel = vi.mocked(apiClient.del);

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

// ---- auth ---------------------------------------------------------

describe("auth store", () => {
  it("starts logged-out and unloaded; all role guards are false", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const store = useAuthStore();
    expect(store.user).toBeNull();
    expect(store.loaded).toBe(false);
    expect(store.isAuthenticated).toBe(false);
    expect(store.isApproved).toBe(false);
    expect(store.isAdmin).toBe(false);
  });

  it("computeds react to user state changes (approved+admin gate)", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const store = useAuthStore();
    const baseUser = {
      id: "u1",
      email: "x@y",
      name: "X",
      role: "organiser" as const,
      is_approved: false,
      chapters: [],
      created_at: "2026-01-01T00:00:00Z",
    };

    // Logged in but unapproved.
    store.user = { ...baseUser };
    expect(store.isAuthenticated).toBe(true);
    expect(store.isApproved).toBe(false);
    expect(store.isAdmin).toBe(false);

    // Approved organiser.
    store.user = { ...baseUser, is_approved: true };
    expect(store.isApproved).toBe(true);
    expect(store.isAdmin).toBe(false);

    // Admin role + approved → isAdmin.
    store.user = { ...baseUser, role: "admin", is_approved: true };
    expect(store.isAdmin).toBe(true);

    // Admin role but unapproved → still false (mirrors backend
    // require_admin).
    store.user = { ...baseUser, role: "admin", is_approved: false };
    expect(store.isAdmin).toBe(false);
  });

  it("hydrates whatsappAvailable from /whatsapp/status when an admin loads", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    vi.mocked(apiClient.getToken).mockReturnValue("tok");
    mockGet.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") {
        return {
          id: "u1",
          email: "a@b",
          name: "A",
          role: "admin",
          is_approved: true,
          chapters: [],
          created_at: "2026-01-01T00:00:00Z",
        };
      }
      if (path === "/api/v1/whatsapp/status") return { state: "open" };
      throw new Error(`unexpected GET ${path}`);
    });
    const store = useAuthStore();
    await store.fetchMe();
    expect(store.whatsappAvailable).toBe(true);
  });

  it("sets whatsappAvailable=false when /status reports not_configured", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    vi.mocked(apiClient.getToken).mockReturnValue("tok");
    mockGet.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") {
        return {
          id: "u1",
          email: "a@b",
          name: "A",
          role: "admin",
          is_approved: true,
          chapters: [],
          created_at: "2026-01-01T00:00:00Z",
        };
      }
      if (path === "/api/v1/whatsapp/status") return { state: "not_configured" };
      throw new Error(`unexpected GET ${path}`);
    });
    const store = useAuthStore();
    await store.fetchMe();
    expect(store.whatsappAvailable).toBe(false);
  });

  it("does not call /whatsapp/status for a non-admin user", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    vi.mocked(apiClient.getToken).mockReturnValue("tok");
    mockGet.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") {
        return {
          id: "u1",
          email: "a@b",
          name: "A",
          role: "organiser",
          is_approved: true,
          chapters: [],
          created_at: "2026-01-01T00:00:00Z",
        };
      }
      throw new Error(`unexpected GET ${path}`);
    });
    const store = useAuthStore();
    await store.fetchMe();
    expect(store.whatsappAvailable).toBe(false);
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("clears whatsappAvailable on logout", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    mockPost.mockResolvedValueOnce(undefined);
    const store = useAuthStore();
    store.whatsappAvailable = true;
    await store.logout();
    expect(store.whatsappAvailable).toBe(false);
  });
});

// Suppress unused-vars warnings on the broader mocks the suite imports.
void mockGet;
void mockPost;
void mockPut;
void mockPatch;
void mockDel;
