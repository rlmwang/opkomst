import { QueryClient } from "@tanstack/svelte-query";

import { ApiError } from "@/api/client";

/**
 * The one query cache.
 *
 * One module rather than something built in the entry, so a composable
 * can reach it without being handed it.
 *
 * Defaults: 60 s stale-time so a dialog opening from a list (and
 * same-list navigation roundtrips) doesn't refetch on mount; retry only
 * on transient (network / 5xx) errors, never on 4xx, which by definition
 * won't become 2xx in the next second and only delays surfacing the real
 * error (a deleted-event slug page sat on "Loading…" for ~1 s before
 * showing "not found"); no refetch-on-window-focus, because organiser
 * tabs sit open all afternoon and refetching every focus would be noisy
 * without solving anything real. Per-key composables override
 * ``staleTime`` where the data is rarer-change (chapters, users) or
 * stricter (mutations always invalidate, so a slightly longer stale
 * window doesn't cause divergence).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
    },
  },
});
