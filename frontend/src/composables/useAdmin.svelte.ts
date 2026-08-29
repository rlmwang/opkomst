import { post } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { mutation } from "@/composables/mutation.svelte";
import type { User } from "@/api/types";

/**
 * How many accounts are waiting on an admin.
 *
 * Fired only when the actor is an admin of an organisation: organisers
 * don't get the badge and shouldn't pay the network round trip. It
 * refetches on the stale-time cadence, so a new sign-up shows up within
 * about 30 seconds on any open admin tab.
 */
export function pendingCountQuery(enabled: () => boolean) {
  return apiQuery<{ count: number }>(
    () => ["admin", "users", "pending-count"],
    () => "/api/v1/admin/users/pending-count",
    { enabled, staleTime: 30_000 },
  );
}

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
    { invalidate: [["admin", "users"]] },
  );
