/**
 * Thin wrapper over `@tanstack/vue-query` for the
 * "fetch this URL, cache by this key" shape that 70 % of our
 * read composables collapse to. Mutations and optimistic
 * updates stay as named composables — they carry real rollback
 * logic that doesn't generalise.
 *
 * Two flavours:
 *
 *   useApiQuery(key, path, opts?)      // queryKey + GET
 *   listOf(query)                      // unwrap data ?? []
 *
 * Both ``key`` and ``path`` accept either a literal or a
 * getter — pass a getter when either depends on a ref so the
 * query reactively re-runs.
 */

import { type QueryKey, keepPreviousData, useQuery } from "@tanstack/vue-query";
import { type ComputedRef, type MaybeRef, computed, unref } from "vue";

import { get } from "@/api/client";

type Source<T> = T | (() => T) | { value: T };

function _resolve<T>(src: Source<T>): T {
  if (typeof src === "function") return (src as () => T)();
  if (src && typeof src === "object" && "value" in (src as object)) {
    return (src as { value: T }).value;
  }
  return src as T;
}

export interface UseApiQueryOpts {
  enabled?: MaybeRef<boolean>;
  /** Pass through to vue-query — ``false`` for forms that 410
   * on a missing token, where one retry is wasted work. */
  retry?: boolean | number;
  /** Keep the previous query's data visible while a new key
   * fetches. Use for parameterised queries (event-by-id, etc.)
   * so navigating from one event to another doesn't flash a
   * skeleton. The new data still replaces the old once the
   * fetch resolves. Defaults to ``true`` because the cost of
   * keeping a few extra DTOs around briefly is trivial and the
   * UX win is worth it; pass ``false`` for queries where the
   * stale value would be actively misleading. */
  placeholderPrevious?: boolean;
  /** Override the default 60s stale-time for queries that want
   * to refetch sooner (poll-ish use cases like the navbar's
   * pending-count indicator). */
  staleTime?: number;
}

export function useApiQuery<T>(
  key: Source<QueryKey>,
  path: Source<string>,
  opts: UseApiQueryOpts = {},
) {
  return useQuery({
    queryKey: computed(() => _resolve(key)),
    queryFn: () => get<T>(_resolve(path)),
    enabled: opts.enabled !== undefined ? computed(() => unref(opts.enabled) ?? true) : undefined,
    retry: opts.retry,
    staleTime: opts.staleTime,
    placeholderData: (opts.placeholderPrevious ?? true) ? keepPreviousData : undefined,
  });
}

/** Unwrap a ``useApiQuery`` result into a non-nullable list. */
export function listOf<T>(query: { data: { value: T[] | undefined } }): ComputedRef<T[]> {
  return computed(() => query.data.value ?? []);
}
