import { defineStore } from "pinia";
import { ref } from "vue";
import { get, post } from "@/api/client";
import type { User } from "@/stores/auth";

export const useAdminStore = defineStore("admin", () => {
  const users = ref<User[]>([]);

  async function fetchUsers(opts: { pending?: boolean } = {}): Promise<void> {
    const qs = opts.pending ? "?pending=true" : "";
    users.value = await get<User[]>(`/api/v1/admin/users${qs}`);
  }

  async function approve(userId: string, afdelingId: string): Promise<void> {
    const updated = await post<User>(`/api/v1/admin/users/${userId}/approve`, {
      afdeling_id: afdelingId,
    });
    users.value = users.value.map((u) => (u.id === userId ? updated : u));
  }

  async function assignAfdeling(userId: string, afdelingId: string): Promise<void> {
    const updated = await post<User>(`/api/v1/admin/users/${userId}/assign-afdeling`, {
      afdeling_id: afdelingId,
    });
    users.value = users.value.map((u) => (u.id === userId ? updated : u));
  }

  async function promote(userId: string): Promise<void> {
    const updated = await post<User>(`/api/v1/admin/users/${userId}/promote`);
    users.value = users.value.map((u) => (u.id === userId ? updated : u));
  }

  async function demote(userId: string): Promise<void> {
    const updated = await post<User>(`/api/v1/admin/users/${userId}/demote`);
    users.value = users.value.map((u) => (u.id === userId ? updated : u));
  }

  return { users, fetchUsers, approve, assignAfdeling, promote, demote };
});
