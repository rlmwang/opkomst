import { del, get, patch, post } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { mutation } from "@/composables/mutation.svelte";
import { queryClient } from "@/lib/query-client";
import type { Chapter, ChapterPatch as ChapterPatchPayload } from "@/api/types";

export type { Chapter, ChapterPatchPayload };

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

export const createChapter = () =>
  mutation((name: string) => post<Chapter>("/api/v1/chapters", { name }), {
    invalidate: [["chapters"]],
  });

export const updateChapter = () =>
  mutation(
    (vars: { id: string; payload: ChapterPatchPayload }) =>
      patch<Chapter>(`/api/v1/chapters/${vars.id}`, vars.payload),
    { invalidate: [["chapters"]] },
  );

/**
 * Archive, with the rows that pointed at the chapter handed somewhere
 * else or left without one.
 *
 * The row leaves every cached list on the click, and every one of them
 * is snapshotted, because the page holds two: the table's live rows and
 * the add bar's archived ones.
 */
export const archiveChapter = () =>
  mutation(
    (vars: { id: string; reassign?: { users?: string | null; events?: string | null } }) =>
      del(`/api/v1/chapters/${vars.id}`, {
        reassign_users_to: vars.reassign?.users ?? null,
        reassign_events_to: vars.reassign?.events ?? null,
      }),
    {
      invalidate: [["chapters"]],
      optimistic: (vars) => {
        const snapshots = queryClient
          .getQueriesData<Chapter[]>({ queryKey: ["chapters"] })
          .map(([key, data]) => ({ key, data }));
        queryClient.setQueriesData<Chapter[]>({ queryKey: ["chapters"] }, (old) =>
          old?.filter((c) => c.id !== vars.id),
        );
        return () => {
          for (const { key, data } of snapshots) queryClient.setQueryData(key, data);
        };
      },
    },
  );

export const restoreChapter = () =>
  mutation((id: string) => post<Chapter>(`/api/v1/chapters/${id}/restore`), {
    invalidate: [["chapters"]],
  });

/** How many users and events point at a chapter. Asked once, when the
 *  delete dialog opens, because the answer decides what it offers. */
export function chapterUsage(id: string): Promise<{ users: number; events: number }> {
  return get<{ users: number; events: number }>(`/api/v1/chapters/${id}/usage`);
}
