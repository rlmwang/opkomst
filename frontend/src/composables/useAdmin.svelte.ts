import { apiQuery } from "@/api/queries.svelte";

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
