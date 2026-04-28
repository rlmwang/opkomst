/**
 * Chapter composables.
 *
 * Replaces ``stores/chapters.ts``. The chapters list is small (≤
 * dozens) so we always fetch the full set; ``includeArchived``
 * just toggles the query string. Mutations invalidate the list so
 * the next render reads fresh data.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, type ComputedRef } from "vue";
import type { Chapter, ChapterPatch as ChapterPatchPayload } from "@/api/types";
import { del, get, patch, post } from "@/api/client";

export type { Chapter, ChapterPatchPayload };

const chaptersKey = (includeArchived: boolean) =>
  ["chapters", { includeArchived }] as const;

const sortByName = (list: Chapter[]): Chapter[] =>
  [...list].sort((a, b) => a.name.localeCompare(b.name));

export function useChapters(opts: { includeArchived?: boolean } = {}) {
  const includeArchived = !!opts.includeArchived;
  return useQuery({
    queryKey: chaptersKey(includeArchived),
    queryFn: async () => {
      const list = await get<Chapter[]>(
        `/api/v1/chapters${includeArchived ? "?include_archived=true" : ""}`,
      );
      return sortByName(list);
    },
  });
}

export function chapterList(
  query: ReturnType<typeof useChapters>,
): ComputedRef<Chapter[]> {
  return computed(() => query.data.value ?? []);
}

export function useCreateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => post<Chapter>("/api/v1/chapters", { name }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["chapters"] }),
  });
}

export function useUpdateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; payload: ChapterPatchPayload }) =>
      patch<Chapter>(`/api/v1/chapters/${vars.id}`, vars.payload),
    onSettled: () => qc.invalidateQueries({ queryKey: ["chapters"] }),
  });
}

export function useArchiveChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      id: string;
      reassign?: { users?: string | null; events?: string | null };
    }) =>
      del(`/api/v1/chapters/${vars.id}`, {
        reassign_users_to: vars.reassign?.users ?? null,
        reassign_events_to: vars.reassign?.events ?? null,
      }),
    onMutate: async (vars) => {
      // Optimistic remove from every cached chapters list.
      await qc.cancelQueries({ queryKey: ["chapters"] });
      const snapshots = qc
        .getQueriesData<Chapter[]>({ queryKey: ["chapters"] })
        .map(([key, data]) => ({ key, data }));
      qc.setQueriesData<Chapter[]>({ queryKey: ["chapters"] }, (old) =>
        old?.filter((a) => a.id !== vars.id),
      );
      return { snapshots };
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshots.forEach(({ key, data }) => qc.setQueryData(key, data));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["chapters"] }),
  });
}

export function useRestoreChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post<Chapter>(`/api/v1/chapters/${id}/restore`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["chapters"] }),
  });
}

export function getChapterUsage(
  id: string,
): Promise<{ users: number; events: number }> {
  return get<{ users: number; events: number }>(`/api/v1/chapters/${id}/usage`);
}
