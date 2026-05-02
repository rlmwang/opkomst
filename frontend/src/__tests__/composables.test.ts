/**
 * Smoke tests for the Vue Query composables.
 *
 * These don't render a component — they directly test that each
 * mutation hits the right URL with the right verb. The HTTP client
 * is mocked. Goal: catch a renamed route or flipped verb at unit-
 * test time, not when the integration suite breaks two refactors
 * later.
 *
 * Vue Query needs a ``QueryClient`` in scope; rather than mount a
 * real component, ``provide`` the client through a tiny
 * ``withSetup`` harness that runs the composable inside a Vue app
 * instance.
 */

import { QueryClient, VUE_QUERY_CLIENT } from "@tanstack/vue-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type App, createApp, defineComponent, h } from "vue";
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
  ApiError: class ApiError extends Error {},
}));

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPut = vi.mocked(apiClient.put);
const mockPatch = vi.mocked(apiClient.patch);
const mockDel = vi.mocked(apiClient.del);

let app: App | null = null;
let queryClient: QueryClient;

/** Run a composable inside a Vue setup. Returns the composable's
 * return value plus the harness app for cleanup. */
function withSetup<T>(composable: () => T): T {
  let result!: T;
  const Harness = defineComponent({
    setup() {
      result = composable();
      return () => h("div");
    },
  });
  app = createApp(Harness);
  app.provide(VUE_QUERY_CLIENT, queryClient);
  app.mount(document.createElement("div"));
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  app?.unmount();
  app = null;
  queryClient.clear();
});

describe("useAdmin composables", () => {
  it("useUsers issues GET /api/v1/admin/users", async () => {
    const { useUsers } = await import("@/composables/useAdmin");
    mockGet.mockResolvedValueOnce([]);

    const q = withSetup(() => useUsers());
    await q.refetch();

    expect(mockGet).toHaveBeenCalledWith("/api/v1/admin/users");
  });

  it("useApproveUser POSTs to /approve with the chapter_ids payload", async () => {
    const { useApproveUser } = await import("@/composables/useAdmin");
    mockPost.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useApproveUser());
    await m.mutateAsync({ userId: "u1", chapterIds: ["ch1", "ch2"] });

    expect(mockPost).toHaveBeenCalledWith("/api/v1/admin/users/u1/approve", {
      chapter_ids: ["ch1", "ch2"],
    });
  });

  it("useSetUserChapters POSTs the full chapter set", async () => {
    const { useSetUserChapters } = await import("@/composables/useAdmin");
    mockPost.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useSetUserChapters());
    await m.mutateAsync({ userId: "u1", chapterIds: ["ch1", "ch2"] });

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/admin/users/u1/set-chapters",
      { chapter_ids: ["ch1", "ch2"] },
    );
  });

  it("useRemoveUser DELETEs /api/v1/admin/users/{id}", async () => {
    const { useRemoveUser } = await import("@/composables/useAdmin");
    mockDel.mockResolvedValueOnce(undefined as never);

    const m = withSetup(() => useRemoveUser());
    await m.mutateAsync("u1");

    expect(mockDel).toHaveBeenCalledWith("/api/v1/admin/users/u1");
  });

  it("useRemoveUser rolls every cached users-list back on failure", async () => {
    const { useRemoveUser } = await import("@/composables/useAdmin");

    // Two cached lists under the same prefix — verify both get
    // rolled back, not just one.
    queryClient.setQueryData(
      ["admin", "users", { pending: false }],
      [{ id: "u1", name: "A" }, { id: "u2", name: "B" }],
    );
    queryClient.setQueryData(
      ["admin", "users", { pending: true }],
      [{ id: "u1", name: "A" }],
    );
    mockDel.mockRejectedValueOnce(new Error("boom"));

    const m = withSetup(() => useRemoveUser());
    await expect(m.mutateAsync("u1")).rejects.toThrow();

    const all = queryClient.getQueryData<{ id: string }[]>([
      "admin",
      "users",
      { pending: false },
    ]);
    const pending = queryClient.getQueryData<{ id: string }[]>([
      "admin",
      "users",
      { pending: true },
    ]);
    expect(all?.map((u) => u.id)).toEqual(["u1", "u2"]);
    expect(pending?.map((u) => u.id)).toEqual(["u1"]);
  });
});

describe("useEvents composables", () => {
  it("useArchiveEvent rolls the cache back to the snapshot on failure", async () => {
    const { useArchiveEvent } = await import("@/composables/useEvents");

    queryClient.setQueryData(
      ["events", "active"],
      [{ id: "e1", name: "A" }, { id: "e2", name: "B" }],
    );
    mockPost.mockRejectedValueOnce(new Error("boom"));

    const m = withSetup(() => useArchiveEvent());
    await expect(m.mutateAsync("e1")).rejects.toThrow();

    // Snapshot restored — both events back in the cache, in order.
    const after = queryClient.getQueryData<{ id: string }[]>(["events", "active"]);
    expect(after?.map((e) => e.id)).toEqual(["e1", "e2"]);
  });

  it("useSendEmailsNow POSTs the channel-keyed URL", async () => {
    const { useSendEmailsNow } = await import("@/composables/useEvents");
    mockPost.mockResolvedValueOnce({ processed: 3 });

    const m = withSetup(() => useSendEmailsNow());
    const r = await m.mutateAsync({ eventId: "ev1", channel: "reminder" });

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/events/ev1/send-emails/reminder",
    );
    expect(r.processed).toBe(3);
  });

  it("useCreateEvent POSTs /api/v1/events with the payload", async () => {
    const { useCreateEvent } = await import("@/composables/useEvents");
    const payload = {
      name: "Demo",
      chapter_id: "ch1",
      topic: null,
      location: "X",
      latitude: null,
      longitude: null,
      starts_at: "2026-05-01T18:00:00Z",
      ends_at: "2026-05-01T20:00:00Z",
      source_options: ["F"],
      help_options: [],
      feedback_enabled: true,
      reminder_enabled: false,
      locale: "nl" as const,
    };
    mockPost.mockResolvedValueOnce({ id: "ev1" });

    const m = withSetup(() => useCreateEvent());
    await m.mutateAsync(payload);

    expect(mockPost).toHaveBeenCalledWith("/api/v1/events", payload);
  });

  it("useUpdateEvent PUTs the event-id-keyed URL", async () => {
    const { useUpdateEvent } = await import("@/composables/useEvents");
    mockPut.mockResolvedValueOnce({ id: "ev1" } as never);

    const m = withSetup(() => useUpdateEvent());
    const payload = { name: "X" } as never;
    await m.mutateAsync({ eventId: "ev1", payload });

    expect(mockPut).toHaveBeenCalledWith("/api/v1/events/ev1", payload);
  });

  it("useRestoreEvent POSTs /api/v1/events/{id}/restore", async () => {
    const { useRestoreEvent } = await import("@/composables/useEvents");
    mockPost.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useRestoreEvent());
    await m.mutateAsync("ev1");

    expect(mockPost).toHaveBeenCalledWith("/api/v1/events/ev1/restore");
  });

  // ``usePublicSignup`` removed: the public sign-up form moved to
  // its own mini-app (``frontend/src/public/``) which uses raw
  // ``fetch`` instead of Vue Query. Coverage for that POST shape
  // lives in the backend's ``test_events_router_extras.py`` /
  // ``test_public_archived.py`` end-to-end tests.
});

describe("useChapters composables", () => {
  it("useArchiveChapter rolls every cached chapters-list back on failure", async () => {
    const { useArchiveChapter } = await import("@/composables/useChapters");

    queryClient.setQueryData(
      ["chapters"],
      [{ id: "c1", name: "A" }, { id: "c2", name: "B" }],
    );
    mockDel.mockRejectedValueOnce(new Error("boom"));

    const m = withSetup(() => useArchiveChapter());
    await expect(m.mutateAsync({ id: "c1" })).rejects.toThrow();

    const after = queryClient.getQueryData<{ id: string }[]>(["chapters"]);
    expect(after?.map((c) => c.id)).toEqual(["c1", "c2"]);
  });

  it("useCreateChapter POSTs /api/v1/chapters with the name body", async () => {
    const { useCreateChapter } = await import("@/composables/useChapters");
    mockPost.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useCreateChapter());
    await m.mutateAsync("New chapter");

    expect(mockPost).toHaveBeenCalledWith("/api/v1/chapters", {
      name: "New chapter",
    });
  });

  it("useUpdateChapter PATCHes /api/v1/chapters/{id} with the payload", async () => {
    const { useUpdateChapter } = await import("@/composables/useChapters");
    mockPatch.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useUpdateChapter());
    await m.mutateAsync({ id: "c1", payload: { name: "Renamed" } });

    expect(mockPatch).toHaveBeenCalledWith("/api/v1/chapters/c1", {
      name: "Renamed",
    });
  });
});

describe("useFeedback composables", () => {
  it("useSubmitFeedback POSTs the URL-encoded token path with answers", async () => {
    const { useSubmitFeedback } = await import("@/composables/useFeedback");
    mockPost.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useSubmitFeedback());
    await m.mutateAsync({
      token: "abc 123/x",
      answers: [{ question_key: "q1", answer_int: 5 }],
    });

    expect(mockPost).toHaveBeenCalledWith("/api/v1/feedback/abc%20123%2Fx/submit", {
      answers: [{ question_key: "q1", answer_int: 5 }],
    });
  });
});
