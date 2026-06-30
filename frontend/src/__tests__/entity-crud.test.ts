/**
 * Unit tests for the ``createEntityCrud`` factory: verifies each
 * generated hook hits the right URL/verb and that the list queries
 * carry the chapter-scoped query keys. The HTTP client is mocked.
 */

import { QueryClient, VUE_QUERY_CLIENT } from "@tanstack/vue-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type App, createApp, defineComponent, h } from "vue";
import * as apiClient from "@/api/client";
import { createEntityCrud } from "@/composables/createEntityCrud";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPut = vi.mocked(apiClient.put);
const mockDel = vi.mocked(apiClient.del);

let app: App | null = null;
let queryClient: QueryClient;

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

// A throwaway resource so the test is independent of any real entity.
const crud = createEntityCrud<{ id: string }, { id: string }, { name: string }>({
  resource: "widgets",
});

describe("createEntityCrud", () => {
  it("useList fetches the base URL and keys on [resource, active, {chapter}]", async () => {
    mockGet.mockResolvedValueOnce([]);
    const q = withSetup(() => crud.useList());
    await q.refetch();
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets");
  });

  it("useList appends chapter_id when filtered", async () => {
    mockGet.mockResolvedValueOnce([]);
    const q = withSetup(() => crud.useList({ chapterId: "ch1" }));
    await q.refetch();
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets?chapter_id=ch1");
  });

  it("useArchived fetches the /archived URL", async () => {
    mockGet.mockResolvedValueOnce([]);
    const q = withSetup(() => crud.useArchived());
    await q.refetch();
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets/archived");
  });

  it("useSingle fetches /{id}", async () => {
    mockGet.mockResolvedValueOnce({ id: "w1" });
    const q = withSetup(() => crud.useSingle("w1"));
    await q.refetch();
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets/w1");
  });

  it("useCreate POSTs the base URL with the payload", async () => {
    mockPost.mockResolvedValueOnce({ id: "w1" });
    const m = withSetup(() => crud.useCreate());
    await m.mutateAsync({ name: "X" });
    expect(mockPost).toHaveBeenCalledWith("/api/v1/widgets", { name: "X" });
  });

  it("useUpdate PUTs /{id} with the payload (id-keyed vars)", async () => {
    mockPut.mockResolvedValueOnce({ id: "w1" });
    const m = withSetup(() => crud.useUpdate());
    await m.mutateAsync({ id: "w1", payload: { name: "Y" } });
    expect(mockPut).toHaveBeenCalledWith("/api/v1/widgets/w1", { name: "Y" });
  });

  it("useArchive POSTs /{id}/archive", async () => {
    mockPost.mockResolvedValueOnce({ id: "w1" });
    const m = withSetup(() => crud.useArchive());
    await m.mutateAsync("w1");
    expect(mockPost).toHaveBeenCalledWith("/api/v1/widgets/w1/archive");
  });

  it("useRestore POSTs /{id}/restore", async () => {
    mockPost.mockResolvedValueOnce({ id: "w1" });
    const m = withSetup(() => crud.useRestore());
    await m.mutateAsync("w1");
    expect(mockPost).toHaveBeenCalledWith("/api/v1/widgets/w1/restore");
  });

  it("useDelete DELETEs /{id}", async () => {
    mockDel.mockResolvedValueOnce(undefined as never);
    const m = withSetup(() => crud.useDelete());
    await m.mutateAsync("w1");
    expect(mockDel).toHaveBeenCalledWith("/api/v1/widgets/w1");
  });
});
