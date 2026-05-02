/**
 * Admin user-management composables.
 *
 * Approve / assign-chapter use the basic ``userMutation`` shape:
 * POST that returns the updated ``User`` and invalidates the
 * cache on settle. The toggle-shaped actions (promote / demote)
 * additionally apply an optimistic patch to the cache so the
 * Admin page's ToggleSwitch flips instantly; rollback on error.
 * Remove carries its own optimistic-drop with snapshot rollback.
 *
 * All shapes share ``USERS_KEY`` so a successful action always
 * lands in the next render.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";
import type { Ref } from "vue";
import { computed } from "vue";

import { del, post } from "@/api/client";
import { listOf, useApiQuery } from "@/api/queries";
import type { User } from "@/api/types";

const USERS_KEY = ["admin", "users"] as const;

const usersKey = (pending: boolean) =>
  ["admin", "users", { pending }] as const;

/** Pending-approval count for the navbar's red-dot indicator.
 * Admin-only: the endpoint returns 403 for organisers, so the
 * ``enabled`` flag matches the matrix to skip the round-trip.
 * 30s staleTime — frequent enough that an admin sees a new
 * sign-up land within half a minute, infrequent enough that
 * idle browser tabs aren't hitting the API every render. */
export function usePendingCount(enabled: Ref<boolean> | boolean) {
  return useApiQuery<{ count: number }>(
    ["admin", "users", "pending-count"],
    "/api/v1/admin/users/pending-count",
    {
      enabled,
      staleTime: 30_000,
    },
  );
}

export function useUsers(opts: { pending?: Ref<boolean> | boolean } = {}) {
  const pending = computed(() =>
    typeof opts.pending === "boolean" ? opts.pending : (opts.pending?.value ?? false),
  );
  return useApiQuery<User[]>(
    () => usersKey(pending.value),
    () => `/api/v1/admin/users${pending.value ? "?pending=true" : ""}`,
  );
}

/** Factory for the "POST a user-action endpoint, refetch list"
 * shape. Variants differ only in the URL and request payload —
 * passed in as ``mutationFn``. */
function userMutation<TVar>(mutationFn: (vars: TVar) => Promise<User>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

export const useApproveUser = () =>
  userMutation((vars: { userId: string; chapterIds: string[] }) =>
    post<User>(`/api/v1/admin/users/${vars.userId}/approve`, { chapter_ids: vars.chapterIds }),
  );

/** Replace the user's full chapter membership set. The backend
 * supports add and remove diffing internally; the frontend only
 * ever sends the resulting set, which keeps the optimistic-update
 * shape simple — diff what changed in the UI, send the result. */
export const useSetUserChapters = () =>
  userMutation((vars: { userId: string; chapterIds: string[] }) =>
    post<User>(
      `/api/v1/admin/users/${vars.userId}/set-chapters`,
      { chapter_ids: vars.chapterIds },
    ),
  );

/** Rename a user's display name. Optimistic patch: the cached
 * row's ``name`` flips immediately so the table redraws without
 * waiting on the server, with snapshot rollback on error. */
export function useRenameUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { userId: string; name: string }) =>
      post<User>(`/api/v1/admin/users/${vars.userId}/rename`, { name: vars.name }),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: USERS_KEY });
      const snapshots = qc
        .getQueriesData<User[]>({ queryKey: USERS_KEY })
        .map(([key, data]) => ({ key, data }));
      qc.setQueriesData<User[]>({ queryKey: USERS_KEY }, (old) =>
        old?.map((u) => (u.id === vars.userId ? { ...u, name: vars.name } : u)),
      );
      return { snapshots };
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshots.forEach(({ key, data }) => qc.setQueryData(key, data));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

/** Optimistic-toggle shape for promote / demote. The
 * ``ToggleSwitch`` flip is the dominant visual cue — waiting on
 * a roundtrip before redrawing the switch makes the UI feel
 * unresponsive. Patch the cached user's role inline; revert if
 * the server rejects. */
function roleToggleMutation(targetRole: "admin" | "organiser", endpoint: "promote" | "demote") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => post<User>(`/api/v1/admin/users/${userId}/${endpoint}`),
    onMutate: async (userId) => {
      await qc.cancelQueries({ queryKey: USERS_KEY });
      const snapshots = qc
        .getQueriesData<User[]>({ queryKey: USERS_KEY })
        .map(([key, data]) => ({ key, data }));
      qc.setQueriesData<User[]>({ queryKey: USERS_KEY }, (old) =>
        old?.map((u) => (u.id === userId ? { ...u, role: targetRole } : u)),
      );
      return { snapshots };
    },
    onError: (_err, _userId, ctx) => {
      ctx?.snapshots.forEach(({ key, data }) => qc.setQueryData(key, data));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

export const usePromoteUser = () => roleToggleMutation("admin", "promote");
export const useDemoteUser = () => roleToggleMutation("organiser", "demote");

export function useRemoveUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => del<void>(`/api/v1/admin/users/${userId}`),
    onMutate: async (userId) => {
      // Optimistic: drop the row immediately. ``cancelQueries``
      // prevents an in-flight refetch from clobbering the
      // intermediate state.
      await qc.cancelQueries({ queryKey: USERS_KEY });
      const snapshots = qc
        .getQueriesData<User[]>({ queryKey: USERS_KEY })
        .map(([key, data]) => ({ key, data }));
      qc.setQueriesData<User[]>({ queryKey: USERS_KEY }, (old) =>
        old?.filter((u) => u.id !== userId),
      );
      return { snapshots };
    },
    onError: (_err, _userId, ctx) => {
      // Rollback every cache entry we touched.
      ctx?.snapshots.forEach(({ key, data }) => qc.setQueryData(key, data));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

export const userList = listOf<User>;
