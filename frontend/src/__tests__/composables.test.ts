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
  app.provide(VUE_QUERY_CLIENT + ":", queryClient);
  // ``provide`` for the default key (no app-level ``inject`` lookup
  // is needed — the symbol ``VUE_QUERY_CLIENT`` is the public key).
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

  it("useApproveUser POSTs to /approve with the chapter_id payload", async () => {
    const { useApproveUser } = await import("@/composables/useAdmin");
    mockPost.mockResolvedValueOnce({} as never);

    const m = withSetup(() => useApproveUser());
    await m.mutateAsync({ userId: "u1", chapterId: "ch1" });

    expect(mockPost).toHaveBeenCalledWith("/api/v1/admin/users/u1/approve", {
      chapter_id: "ch1",
    });
  });

  it("useRemoveUser DELETEs /api/v1/admin/users/{id}", async () => {
    const { useRemoveUser } = await import("@/composables/useAdmin");
    mockDel.mockResolvedValueOnce(undefined as never);

    const m = withSetup(() => useRemoveUser());
    await m.mutateAsync("u1");

    expect(mockDel).toHaveBeenCalledWith("/api/v1/admin/users/u1");
  });
});
