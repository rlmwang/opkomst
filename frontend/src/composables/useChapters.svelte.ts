import { apiQuery } from "@/api/queries.svelte";
import type { Chapter } from "@/api/types";

export type { Chapter };

/**
 * The organisation's chapters.
 *
 * The list is small (dozens at most) so the full set is always fetched;
 * ``includeArchived`` just toggles the query string. Mutations
 * invalidate ``["chapters"]`` so the next render reads fresh data.
 *
 * ``enabled`` is how a page with no chapters says so: the endpoint
 * belongs to organisations, and a personal account, or a visitor with no
 * account at all, would only ever get a 404 from it.
 */
export function chaptersQuery(
  opts: { includeArchived?: boolean; enabled?: () => boolean } = {},
) {
  const includeArchived = !!opts.includeArchived;
  return apiQuery<Chapter[]>(
    () => ["chapters", { includeArchived }],
    () => `/api/v1/chapters${includeArchived ? "?include_archived=true" : ""}`,
    { enabled: opts.enabled },
  );
}

/** Sorted list, empty while loading. The SQL list isn't sorted (the
 *  router does no ORDER BY) and the dropdown wants alphabetical. */
export function sortedChapters(list: Chapter[] | undefined): Chapter[] {
  return [...(list ?? [])].sort((a, b) => a.name.localeCompare(b.name));
}
