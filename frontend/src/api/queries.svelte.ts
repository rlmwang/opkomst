import { createQuery, type QueryKey } from "@tanstack/svelte-query";

import { get } from "@/api/client";
import { queryClient } from "@/lib/query-client";

/**
 * A GET against the app's API, as Svelte sees it.
 *
 * The client is passed explicitly rather than taken from context, so a
 * composable can be called from anywhere without a provider above it.
 *
 * Reactive inputs are functions, which is Svelte 5's shape and
 * svelte-query's: the options are re-read whenever the state they touch
 * changes, and a page reads ``query.data`` like any other reactive value.
 */
export interface ApiQueryOpts {
  enabled?: () => boolean;
  staleTime?: number;
  retry?: number | boolean;
}

export interface ApiQuery<T> {
  readonly data: T | undefined;
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: Error | null;
  /** Ask again now, and hand back what came back. */
  refetch: () => Promise<T | undefined>;
}

export function apiQuery<T>(
  key: () => QueryKey,
  path: () => string,
  opts: ApiQueryOpts = {},
): ApiQuery<T> {
  const query = createQuery<T>(
    () => ({
      queryKey: key(),
      queryFn: () => get<T>(path()),
      enabled: opts.enabled ? opts.enabled() : true,
      staleTime: opts.staleTime,
      retry: opts.retry,
    }),
    () => queryClient,
  );

  return {
    get data() {
      return query.data;
    },
    get isPending() {
      return query.isPending;
    },
    get isError() {
      return query.isError;
    },
    get error() {
      return query.error;
    },
    refetch: async () => (await query.refetch()).data,
  };
}
