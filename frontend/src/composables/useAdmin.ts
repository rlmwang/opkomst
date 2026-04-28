/**
 * Admin user-management composables.
 *
 * Replaces ``stores/admin.ts``. The store's mutation actions
 * (approve / assign-chapter / promote / demote / remove) used to
 * mutate the local ``users.value`` array unconditionally — if the
 * server call failed, the local list silently diverged from the
 * server. Vue Query's ``onMutate`` / ``onError`` / ``onSettled``
 * hooks make rollback structural: optimistic mutation flips the
 * cache, an error reverts it, every settle invalidates so the next
 * render reads the truth.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { Ref } from "vue";
import { computed, type ComputedRef } from "vue";
import type { User } from "@/api/types";
import { del, get, post } from "@/api/client";

const usersKey = (pending?: boolean) =>
  ["admin", "users", { pending: !!pending }] as const;

export function useUsers(opts: { pending?: Ref<boolean> | boolean } = {}) {
  const pending = computed(() =>
    typeof opts.pending === "boolean" ? opts.pending : (opts.pending?.value ?? false),
  );
  return useQuery({
    queryKey: computed(() => usersKey(pending.value)),
    queryFn: () =>
      get<User[]>(`/api/v1/admin/users${pending.value ? "?pending=true" : ""}`),
  });
}

export function useApproveUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { userId: string; chapterId: string }) =>
      post<User>(`/api/v1/admin/users/${vars.userId}/approve`, {
        chapter_id: vars.chapterId,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

export function useAssignChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { userId: string; chapterId: string }) =>
      post<User>(`/api/v1/admin/users/${vars.userId}/assign-chapter`, {
        chapter_id: vars.chapterId,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

export function usePromoteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      post<User>(`/api/v1/admin/users/${userId}/promote`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

export function useDemoteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      post<User>(`/api/v1/admin/users/${userId}/demote`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

export function useRemoveUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => del<void>(`/api/v1/admin/users/${userId}`),
    onMutate: async (userId) => {
      // Optimistic: drop the row immediately. ``cancelQueries``
      // prevents an in-flight refetch from clobbering the
      // intermediate state.
      await qc.cancelQueries({ queryKey: ["admin", "users"] });
      const snapshots = qc
        .getQueriesData<User[]>({ queryKey: ["admin", "users"] })
        .map(([key, data]) => ({ key, data }));
      qc.setQueriesData<User[]>({ queryKey: ["admin", "users"] }, (old) =>
        old?.filter((u) => u.id !== userId),
      );
      return { snapshots };
    },
    onError: (_err, _userId, ctx) => {
      // Rollback every cache entry we touched.
      ctx?.snapshots.forEach(({ key, data }) => qc.setQueryData(key, data));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

// Helper that flattens a useQuery result into a non-nullable list.
// Most callsites want "the users" with [] as the empty state — this
// drops the ``data | undefined`` ceremony at every consumer.
export function userList(query: ReturnType<typeof useUsers>): ComputedRef<User[]> {
  return computed(() => query.data.value ?? []);
}
