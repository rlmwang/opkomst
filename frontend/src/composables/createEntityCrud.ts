/**
 * Entity CRUD composable factory.
 *
 * Events / Forms / Datepolls / Rosters are chapter-scoped, archivable
 * resources with an identical Vue Query surface: an active list and an
 * archived list (both filterable by chapter), a single fetch, and the
 * create / update / archive / restore / delete mutations that each
 * invalidate the resource's caches. This factory generates that common
 * surface from one ``resource`` string so each entity composable is its
 * factory call plus only the bits that genuinely differ (entity-specific
 * reads like stats/summaries, public-by-slug, and any optimistic
 * mutations — e.g. events keeps its own optimistic update/archive/delete).
 *
 * Query keys: ``[resource, "active", {chapter}]`` / ``[resource,
 * "archived", {chapter}]`` / ``[resource, "single", id]``. ``update``
 * takes ``{ id, payload }``; ``archive`` / ``restore`` / ``delete`` take
 * a bare id string.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { type MaybeRef, unref } from "vue";

import { del, post, put } from "@/api/client";
import { useApiQuery } from "@/api/queries";

export function createEntityCrud<TList, TSingle, TCreate, TUpdate = TCreate>(opts: {
  resource: string;
}) {
  const { resource } = opts;
  const base = `/api/v1/${resource}`;

  const invalidateLists = (qc: ReturnType<typeof useQueryClient>) =>
    qc.invalidateQueries({ queryKey: [resource] });

  /** Active list, chapter-scoped. ``chapterId`` null/undefined = every
   * chapter the user belongs to. The filter is in the query key so
   * changing the dropdown produces a fresh cache entry. */
  function useList(
    o: { enabled?: MaybeRef<boolean>; chapterId?: MaybeRef<string | null> } = {},
  ) {
    return useApiQuery<TList[]>(
      () => [resource, "active", { chapter: unref(o.chapterId) ?? null }],
      () => {
        const cid = unref(o.chapterId);
        return cid ? `${base}?chapter_id=${encodeURIComponent(cid)}` : base;
      },
      { enabled: o.enabled },
    );
  }

  function useArchived(o: { chapterId?: MaybeRef<string | null> } = {}) {
    return useApiQuery<TList[]>(
      () => [resource, "archived", { chapter: unref(o.chapterId) ?? null }],
      () => {
        const cid = unref(o.chapterId);
        return cid
          ? `${base}/archived?chapter_id=${encodeURIComponent(cid)}`
          : `${base}/archived`;
      },
    );
  }

  function useSingle(id: MaybeRef<string>) {
    return useApiQuery<TSingle>(
      () => [resource, "single", unref(id)],
      () => `${base}/${unref(id)}`,
    );
  }

  function useCreate() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (payload: TCreate) => post<TSingle>(base, payload),
      onSettled: () => invalidateLists(qc),
    });
  }

  function useUpdate() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (vars: { id: string; payload: TUpdate }) =>
        put<TSingle>(`${base}/${vars.id}`, vars.payload),
      onSettled: () => invalidateLists(qc),
    });
  }

  function useArchive() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (id: string) => post<TSingle>(`${base}/${id}/archive`),
      onSettled: () => invalidateLists(qc),
    });
  }

  function useRestore() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (id: string) => post<TSingle>(`${base}/${id}/restore`),
      onSettled: () => invalidateLists(qc),
    });
  }

  function useDelete() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (id: string) => del<void>(`${base}/${id}`),
      onSettled: () => invalidateLists(qc),
    });
  }

  return {
    invalidateLists,
    useList,
    useArchived,
    useSingle,
    useCreate,
    useUpdate,
    useArchive,
    useRestore,
    useDelete,
  };
}
