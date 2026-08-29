/**
 * The ``createEntityCrud`` factory: each generated call hits the right
 * URL and verb, and the list queries carry the chapter-scoped keys. The
 * HTTP client is mocked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@/api/client";
import { createEntityCrud } from "@/composables/createEntityCrud.svelte";
import { queryClient } from "@/lib/query-client";
import { inEffect } from "@/__tests__/effect-root.svelte";

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

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  queryClient.clear();
});

// A throwaway resource, so the test is independent of any real entity.
const crud = createEntityCrud<{ id: string }, { id: string }, { name: string }>({
  resource: "widgets",
});

describe("createEntityCrud", () => {
  it("list fetches the base URL", async () => {
    mockGet.mockResolvedValueOnce([]);
    await inEffect(async () => {
      await crud.list().refetch();
    });
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets");
  });

  it("list appends chapter_id when filtered", async () => {
    mockGet.mockResolvedValueOnce([]);
    await inEffect(async () => {
      await crud.list({ chapterId: () => "ch1" }).refetch();
    });
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets?chapter_id=ch1");
  });

  it("archived fetches the /archived URL", async () => {
    mockGet.mockResolvedValueOnce([]);
    await inEffect(async () => {
      await crud.archived().refetch();
    });
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets/archived");
  });

  it("single fetches /{id}", async () => {
    mockGet.mockResolvedValueOnce({ id: "w1" });
    await inEffect(async () => {
      await crud.single(() => "w1").refetch();
    });
    expect(mockGet).toHaveBeenCalledWith("/api/v1/widgets/w1");
  });

  it("create posts the base URL with the payload", async () => {
    mockPost.mockResolvedValueOnce({ id: "w1" });
    await inEffect(() => crud.create().run({ name: "X" }));
    expect(mockPost).toHaveBeenCalledWith("/api/v1/widgets", { name: "X" });
  });

  it("update puts /{id} with the payload", async () => {
    mockPut.mockResolvedValueOnce({ id: "w1" });
    await inEffect(() => crud.update().run({ id: "w1", payload: { name: "Y" } }));
    expect(mockPut).toHaveBeenCalledWith("/api/v1/widgets/w1", { name: "Y" });
  });

  it("archive posts /{id}/archive", async () => {
    mockPost.mockResolvedValueOnce({ id: "w1" });
    await inEffect(() => crud.archive().run("w1"));
    expect(mockPost).toHaveBeenCalledWith("/api/v1/widgets/w1/archive");
  });

  it("restore posts /{id}/restore", async () => {
    mockPost.mockResolvedValueOnce({ id: "w1" });
    await inEffect(() => crud.restore().run("w1"));
    expect(mockPost).toHaveBeenCalledWith("/api/v1/widgets/w1/restore");
  });

  it("remove deletes /{id}", async () => {
    mockDel.mockResolvedValueOnce(undefined as never);
    await inEffect(() => crud.remove().run("w1"));
    expect(mockDel).toHaveBeenCalledWith("/api/v1/widgets/w1");
  });
});
