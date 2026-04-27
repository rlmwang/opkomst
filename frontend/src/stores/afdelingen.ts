import { defineStore } from "pinia";
import { ref } from "vue";
import { del, get, patch, post } from "@/api/client";

export interface Afdeling {
  id: string; // entity_id (stable across versions)
  name: string;
  archived: boolean;
}

export const useAfdelingenStore = defineStore("afdelingen", () => {
  const all = ref<Afdeling[]>([]);

  async function fetchAll(includeArchived = false): Promise<void> {
    const qs = includeArchived ? "?include_archived=true" : "";
    all.value = await get<Afdeling[]>(`/api/v1/afdelingen${qs}`);
  }

  async function search(query: string, includeArchived = true): Promise<Afdeling[]> {
    // Plain in-memory filter for now — afdelingen lists stay small;
    // refetch (with archived) and filter client-side.
    const list = await get<Afdeling[]>(
      `/api/v1/afdelingen${includeArchived ? "?include_archived=true" : ""}`,
    );
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((a) => a.name.toLowerCase().includes(q));
  }

  async function create(name: string): Promise<Afdeling> {
    const created = await post<Afdeling>("/api/v1/afdelingen", { name });
    all.value = [...all.value, created].sort((a, b) => a.name.localeCompare(b.name));
    return created;
  }

  async function rename(id: string, name: string): Promise<Afdeling> {
    const updated = await patch<Afdeling>(`/api/v1/afdelingen/${id}`, { name });
    all.value = all.value
      .map((a) => (a.id === id ? updated : a))
      .sort((a, b) => a.name.localeCompare(b.name));
    return updated;
  }

  async function getUsage(id: string): Promise<{ users: number; events: number }> {
    return get<{ users: number; events: number }>(`/api/v1/afdelingen/${id}/usage`);
  }

  async function archive(
    id: string,
    reassign?: { users?: string | null; events?: string | null },
  ): Promise<void> {
    await del(`/api/v1/afdelingen/${id}`, {
      reassign_users_to: reassign?.users ?? null,
      reassign_events_to: reassign?.events ?? null,
    });
    all.value = all.value.filter((a) => a.id !== id);
  }

  async function restore(id: string): Promise<Afdeling> {
    const restored = await post<Afdeling>(`/api/v1/afdelingen/${id}/restore`);
    if (!all.value.find((a) => a.id === id)) {
      all.value = [...all.value, restored].sort((a, b) => a.name.localeCompare(b.name));
    } else {
      all.value = all.value.map((a) => (a.id === id ? restored : a));
    }
    return restored;
  }

  return { all, fetchAll, search, create, rename, archive, restore, getUsage };
});
