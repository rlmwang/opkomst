import { createQuery, type QueryKey } from "@tanstack/svelte-query";
import { toStore } from "svelte/store";

import { get } from "@/api/client";
import { queryClient } from "@/lib/query-client";

/**
 * A GET against the app's API, as Svelte sees it.
 *
 * The client is passed explicitly rather than taken from context, so a
 * composable can be called from anywhere without a provider above it.
 *
 * Reactive inputs are functions, which is Svelte 5's shape. This
 * adapter's version of svelte-query still speaks the store contract, so
 * ``toStore`` turns the getter into one: the options are re-read
 * whenever the state they touch changes, and the query re-runs.
 */
export interface ApiQueryOpts {
  enabled?: () => boolean;
  staleTime?: number;
  retry?: number | boolean;
}

export function apiQuery<T>(
  key: () => QueryKey,
  path: () => string,
  opts: ApiQueryOpts = {},
) {
  return createQuery(
    toStore(() => ({
      queryKey: key(),
      queryFn: () => get<T>(path()),
      enabled: opts.enabled ? opts.enabled() : true,
      staleTime: opts.staleTime,
      retry: opts.retry,
    })),
    queryClient,
  );
}
