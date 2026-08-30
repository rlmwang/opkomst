import { del, post } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { mutation } from "@/composables/mutation.svelte";
import { queryClient } from "@/lib/query-client";
import type { User } from "@/api/types";

/**
 * The admin's user list, and everything that can be done to a row of
 * it.
 *
 * Every write patches the cache before the server answers, because each
 * one is a switch, a name or a row the admin is looking at while they
 * click. The patches all go through ``patchUsers``, which is where the
 * one subtlety lives.
 */
const USERS_KEY = ["admin", "users"];

/**
 * Patch every cached user list, and hand back the undo.
 *
 * ``["admin", "users"]`` matches by prefix, and the pending count lives
 * at ``["admin", "users", "pending-count"]``, so it is caught too. Its
 * data is a ``{count}``, not an array, which is why the updater checks
 * before it transforms. Without that check the call throws, the write
 * never runs, and the toast blames the server.
 */
function patchUsers(update: (users: User[]) => User[]): () => void {
  const snapshots = queryClient
    .getQueriesData<User[]>({ queryKey: USERS_KEY })
    .map(([key, data]) => ({ key, data }));
  queryClient.setQueriesData<User[]>({ queryKey: USERS_KEY }, (old) =>
    Array.isArray(old) ? update(old) : old,
  );
  return () => {
    for (const { key, data } of snapshots) queryClient.setQueryData(key, data);
  };
}

/**
 * How many accounts are waiting on an admin.
 *
 * Fired only when the actor is an admin of an organisation: the
 * endpoint refuses an organiser, and the badge is not theirs. On a
 * 30-second stale time, so a new sign-up shows up within half a minute
 * on an open tab without an idle one asking every render.
 */
export function pendingCountQuery(enabled: () => boolean) {
  return apiQuery<{ count: number }>(
    () => ["admin", "users", "pending-count"],
    () => "/api/v1/admin/users/pending-count",
    { enabled, staleTime: 30_000 },
  );
}

export function usersQuery(opts: { pending?: () => boolean } = {}) {
  const pending = () => opts.pending?.() ?? false;
  return apiQuery<User[]>(
    () => ["admin", "users", { pending: pending() }],
    () => `/api/v1/admin/users${pending() ? "?pending=true" : ""}`,
  );
}

/** Approve, into the chapters the admin picked. The approval email
 *  goes out from the endpoint, so the rename has to happen first. */
export const approveUser = () =>
  mutation(
    (vars: { userId: string; chapterIds: string[] }) =>
      post<User>(`/api/v1/admin/users/${vars.userId}/approve`, { chapter_ids: vars.chapterIds }),
    { invalidate: [USERS_KEY] },
  );

/**
 * Replace a user's chapter membership with the given set.
 *
 * The backend works out what was added and what was removed; the app
 * only ever sends the result, which is what the picker holds anyway.
 */
export const setUserChapters = () =>
  mutation(
    (vars: { userId: string; chapterIds: string[] }) =>
      post<User>(`/api/v1/admin/users/${vars.userId}/set-chapters`, {
        chapter_ids: vars.chapterIds,
      }),
    { invalidate: [USERS_KEY] },
  );

export const renameUser = () =>
  mutation(
    (vars: { userId: string; name: string }) =>
      post<User>(`/api/v1/admin/users/${vars.userId}/rename`, { name: vars.name }),
    {
      invalidate: [USERS_KEY],
      optimistic: (vars) =>
        patchUsers((users) =>
          users.map((u) => (u.id === vars.userId ? { ...u, name: vars.name } : u)),
        ),
    },
  );

/** Promote and demote. The switch flipping is the whole of the
 *  feedback, so it flips now and reverts if the server says no. */
function roleToggle(role: "admin" | "organiser", endpoint: "promote" | "demote") {
  return mutation(
    (userId: string) => post<User>(`/api/v1/admin/users/${userId}/${endpoint}`),
    {
      invalidate: [USERS_KEY],
      optimistic: (userId) =>
        patchUsers((users) => users.map((u) => (u.id === userId ? { ...u, role } : u))),
    },
  );
}

export const promoteUser = () => roleToggle("admin", "promote");
export const demoteUser = () => roleToggle("organiser", "demote");

export const removeUser = () =>
  mutation((userId: string) => del<void>(`/api/v1/admin/users/${userId}`), {
    invalidate: [USERS_KEY],
    optimistic: (userId) => patchUsers((users) => users.filter((u) => u.id !== userId)),
  });
