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
    expect(store.isVerified).toBe(false);
    expect(store.isApproved).toBe(false);
    expect(store.isAdmin).toBe(false);
  });

  it("computeds react to user state changes (verified+approved+admin all gate)", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const store = useAuthStore();
    const baseUser = {
      id: "u1",
      email: "x@y",
      name: "X",
      role: "organiser" as const,
      email_verified_at: null,
      is_approved: false,
      chapter_id: null,
      chapter_name: null,
      created_at: "2026-01-01T00:00:00Z",
    };

    // Logged in but unverified + unapproved.
    store.user = { ...baseUser };
    expect(store.isAuthenticated).toBe(true);
    expect(store.isVerified).toBe(false);
    expect(store.isApproved).toBe(false);
    expect(store.isAdmin).toBe(false);

    // Verified only.
    store.user = { ...baseUser, email_verified_at: "2026-01-01T00:00:00Z" };
    expect(store.isVerified).toBe(true);
    expect(store.isApproved).toBe(false);

    // Verified + approved.
    store.user = { ...baseUser, email_verified_at: "2026-01-01T00:00:00Z", is_approved: true };
    expect(store.isApproved).toBe(true);
    expect(store.isAdmin).toBe(false); // role still organiser

    // Admin role + verified + approved → isAdmin.
    store.user = {
      ...baseUser,
      role: "admin",
      email_verified_at: "2026-01-01T00:00:00Z",
      is_approved: true,
    };
    expect(store.isAdmin).toBe(true);

    // Admin role but unverified → still false (mirrors backend require_admin).
    store.user = { ...baseUser, role: "admin", is_approved: true };
    expect(store.isAdmin).toBe(false);
  });
});

// ---- admin --------------------------------------------------------

describe("admin store", () => {
  it("fetchUsers calls GET /api/v1/admin/users and stores the response", async () => {
    const { useAdminStore } = await import("@/stores/admin");
    const store = useAdminStore();
    mockGet.mockResolvedValueOnce([{ id: "u1", name: "X" } as never]);

    await store.fetchUsers();

    expect(mockGet).toHaveBeenCalledWith("/api/v1/admin/users");
    expect(store.users).toHaveLength(1);
  });

  it("fetchUsers passes ?pending=true when opted in", async () => {
    const { useAdminStore } = await import("@/stores/admin");
    const store = useAdminStore();
    mockGet.mockResolvedValueOnce([]);

    await store.fetchUsers({ pending: true });

    expect(mockGet).toHaveBeenCalledWith("/api/v1/admin/users?pending=true");
  });

  it("approve POSTs to /approve and replaces the local row", async () => {
    const { useAdminStore } = await import("@/stores/admin");
    const store = useAdminStore();
    store.users = [{ id: "u1", name: "Old" } as never];
    mockPost.mockResolvedValueOnce({ id: "u1", name: "New" } as never);

    await store.approve("u1", "ch1");

    expect(mockPost).toHaveBeenCalledWith("/api/v1/admin/users/u1/approve", {
      chapter_id: "ch1",
    });
    expect(store.users[0]).toMatchObject({ name: "New" });
  });
});

// ---- chapters -----------------------------------------------------

describe("chapters store", () => {
  it("fetchAll calls GET /api/v1/chapters and stores the response", async () => {
    const { useChaptersStore } = await import("@/stores/chapters");
    const store = useChaptersStore();
    mockGet.mockResolvedValueOnce([{ id: "ch1", name: "A" } as never]);

    await store.fetchAll();

    expect(mockGet).toHaveBeenCalledWith("/api/v1/chapters");
    expect(store.all).toHaveLength(1);
  });

  it("fetchAll passes ?include_archived=true when opted in", async () => {
    const { useChaptersStore } = await import("@/stores/chapters");
    const store = useChaptersStore();
    mockGet.mockResolvedValueOnce([]);

    await store.fetchAll(true);

    expect(mockGet).toHaveBeenCalledWith("/api/v1/chapters?include_archived=true");
  });
});

// ---- events -------------------------------------------------------

describe("events store", () => {
  it("fetchAll calls GET /api/v1/events", async () => {
    const { useEventsStore } = await import("@/stores/events");
    const store = useEventsStore();
    mockGet.mockResolvedValueOnce([]);

    await store.fetchAll();

    expect(mockGet).toHaveBeenCalledWith("/api/v1/events");
  });

  it("sendEmailsNow POSTs the right channel-keyed URL", async () => {
    const { useEventsStore } = await import("@/stores/events");
    const store = useEventsStore();
    mockPost.mockResolvedValueOnce({ processed: 3 });

    const r = await store.sendEmailsNow("ev1", "reminder");

    expect(mockPost).toHaveBeenCalledWith("/api/v1/events/ev1/send-emails/reminder");
    expect(r.processed).toBe(3);
  });
});

// ---- feedback -----------------------------------------------------

describe("feedback store", () => {
  it("fetchQuestions calls GET /api/v1/feedback/questions", async () => {
    const { useFeedbackStore } = await import("@/stores/feedback");
    const store = useFeedbackStore();
    mockGet.mockResolvedValueOnce([]);

    await store.fetchQuestions();

    expect(mockGet).toHaveBeenCalledWith("/api/v1/feedback/questions");
  });

  it("getForm hits /api/v1/feedback/{token} with token-encoded path", async () => {
    const { useFeedbackStore } = await import("@/stores/feedback");
    const store = useFeedbackStore();
    mockGet.mockResolvedValueOnce({ event_name: "X" } as never);

    await store.getForm("abc 123/with-slash");

    expect(mockGet).toHaveBeenCalledWith(
      "/api/v1/feedback/abc%20123%2Fwith-slash",
    );
  });

  it("submit hits /submit and POSTs the answers", async () => {
    const { useFeedbackStore } = await import("@/stores/feedback");
    const store = useFeedbackStore();
    mockPost.mockResolvedValueOnce({} as never);

    await store.submit("tok", [{ question_id: "q1", answer_int: 5 }]);

    expect(mockPost).toHaveBeenCalledWith("/api/v1/feedback/tok/submit", {
      answers: [{ question_id: "q1", answer_int: 5 }],
    });
  });

  it("getPreview targets the slug-scoped preview endpoint", async () => {
    const { useFeedbackStore } = await import("@/stores/feedback");
    const store = useFeedbackStore();
    mockGet.mockResolvedValueOnce({} as never);

    await store.getPreview("my-slug");

    expect(mockGet).toHaveBeenCalledWith(
      "/api/v1/events/by-slug/my-slug/feedback-preview",
    );
  });
});

// Suppress unused-vars warnings on the broader mocks the suite imports.
void mockPut;
void mockPatch;
void mockDel;
