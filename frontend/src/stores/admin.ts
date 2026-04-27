import { defineStore } from "pinia";
import { ref } from "vue";
import { del, get, post } from "@/api/client";
import type { User } from "@/stores/auth";

export const useAdminStore = defineStore("admin", () => {
  const users = ref<User[]>([]);

  async function fetchUsers(opts: { pending?: boolean } = {}): Promise<void> {
    const qs = opts.pending ? "?pending=true" : "";
    users.value = await get<User[]>(`/api/v1/admin/users${qs}`);
  }

  async function approve(userId: string, chapterId: string): Promise<void> {
    const updated = await post<User>(`/api/v1/admin/users/${userId}/approve`, {
      chapter_id: chapterId,
    });
    users.value = users.value.map((u) => (u.id === userId ? updated : u));
  }

  async function assignChapter(userId: string, chapterId: string): Promise<void> {
    const updated = await post<User>(`/api/v1/admin/users/${userId}/assign-chapter`, {
      chapter_id: chapterId,
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

  async function remove(userId: string): Promise<void> {
    await del<void>(`/api/v1/admin/users/${userId}`);
    users.value = users.value.filter((u) => u.id !== userId);
  }

  return { users, fetchUsers, approve, assignChapter, promote, demote, remove };
});
