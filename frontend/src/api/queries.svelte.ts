import { createQuery, type QueryKey } from "@tanstack/svelte-query";
import { fromStore, toStore } from "svelte/store";

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
 * the getter goes in through ``toStore`` and the result comes back out
 * through ``fromStore``: the options are re-read whenever the state they
 * touch changes, and a page reads ``query.data`` like any other reactive
 * value instead of carrying a store's ``$`` through every template. The
 * two conversions are the whole of the adapter, and both go away if the
 * library grows a runes API.
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
  const store = fromStore(
    createQuery<T>(
      toStore(() => ({
        queryKey: key(),
        queryFn: () => get<T>(path()),
        enabled: opts.enabled ? opts.enabled() : true,
        staleTime: opts.staleTime,
        retry: opts.retry,
      })),
      queryClient,
    ),
  );

  return {
    get data() {
      return store.current.data;
    },
    get isPending() {
      return store.current.isPending;
    },
    get isError() {
      return store.current.isError;
    },
    get error() {
      return store.current.error;
    },
    refetch: async () => (await store.current.refetch()).data,
  };
}
