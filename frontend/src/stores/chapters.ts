import { defineStore } from "pinia";
import { ref } from "vue";
import type { Chapter, ChapterPatch as ChapterPatchPayload } from "@/api/types";
import { del, get, patch, post } from "@/api/client";

export type { Chapter, ChapterPatchPayload };

export const useChaptersStore = defineStore("chapters", () => {
  const all = ref<Chapter[]>([]);

  async function fetchAll(includeArchived = false): Promise<void> {
    const qs = includeArchived ? "?include_archived=true" : "";
    all.value = await get<Chapter[]>(`/api/v1/chapters${qs}`);
  }

  async function search(query: string, includeArchived = true): Promise<Chapter[]> {
    // Plain in-memory filter for now — chapters lists stay small;
    // refetch (with archived) and filter client-side.
    const list = await get<Chapter[]>(
      `/api/v1/chapters${includeArchived ? "?include_archived=true" : ""}`,
    );
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((a) => a.name.toLowerCase().includes(q));
  }

  async function create(name: string): Promise<Chapter> {
    const created = await post<Chapter>("/api/v1/chapters", { name });
    all.value = [...all.value, created].sort((a, b) => a.name.localeCompare(b.name));
    return created;
  }

  async function rename(id: string, name: string): Promise<Chapter> {
    return updatePatch(id, { name });
  }

  async function updatePatch(id: string, payload: ChapterPatchPayload): Promise<Chapter> {
    const updated = await patch<Chapter>(`/api/v1/chapters/${id}`, payload);
    all.value = all.value
      .map((a) => (a.id === id ? updated : a))
      .sort((a, b) => a.name.localeCompare(b.name));
    return updated;
  }

  async function getUsage(id: string): Promise<{ users: number; events: number }> {
    return get<{ users: number; events: number }>(`/api/v1/chapters/${id}/usage`);
  }

  async function archive(
    id: string,
    reassign?: { users?: string | null; events?: string | null },
  ): Promise<void> {
    await del(`/api/v1/chapters/${id}`, {
      reassign_users_to: reassign?.users ?? null,
      reassign_events_to: reassign?.events ?? null,
    });
    all.value = all.value.filter((a) => a.id !== id);
  }

  async function restore(id: string): Promise<Chapter> {
    const restored = await post<Chapter>(`/api/v1/chapters/${id}/restore`);
    if (!all.value.find((a) => a.id === id)) {
      all.value = [...all.value, restored].sort((a, b) => a.name.localeCompare(b.name));
    } else {
      all.value = all.value.map((a) => (a.id === id ? restored : a));
    }
    return restored;
  }

  return { all, fetchAll, search, create, rename, updatePatch, archive, restore, getUsage };
});
