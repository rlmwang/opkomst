import { del, post, put } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { queryClient } from "@/lib/query-client";

import { mutation } from "./mutation.svelte";

/**
 * Entity CRUD factory.
 *
 * Events, forms, datepolls and rosters are chapter-scoped, archivable
 * resources with an identical query surface: an active list and an
 * archived list (both filterable by chapter), a single fetch, and the
 * create, update, archive, restore and delete writes that each
 * invalidate the resource's caches. This generates that common surface
 * from one ``resource`` string, so each entity's own module is this call
 * plus only what genuinely differs: entity-specific reads like stats and
 * summaries, public-by-slug, and any optimistic write.
 *
 * Query keys: ``[resource, "active", {chapter}]``, ``[resource,
 * "archived", {chapter}]``, ``[resource, "single", id]``.
 */
export function createEntityCrud<TList, TSingle, TCreate, TUpdate = TCreate>(opts: {
  resource: string;
}) {
  const { resource } = opts;
  const base = `/api/v1/${resource}`;
  const invalidateLists = () => void queryClient.invalidateQueries({ queryKey: [resource] });

  /** Active list, chapter-scoped. A null chapter is every chapter the
   *  user belongs to. The filter is in the query key, so changing the
   *  dropdown produces a fresh cache entry. */
  function list(o: { enabled?: () => boolean; chapterId?: () => string | null } = {}) {
    return apiQuery<TList[]>(
      () => [resource, "active", { chapter: o.chapterId?.() ?? null }],
      () => {
        const cid = o.chapterId?.();
        return cid ? `${base}?chapter_id=${encodeURIComponent(cid)}` : base;
      },
      { enabled: o.enabled },
    );
  }

  function archived(o: { chapterId?: () => string | null } = {}) {
    return apiQuery<TList[]>(
      () => [resource, "archived", { chapter: o.chapterId?.() ?? null }],
      () => {
        const cid = o.chapterId?.();
        return cid ? `${base}/archived?chapter_id=${encodeURIComponent(cid)}` : `${base}/archived`;
      },
    );
  }

  /** One row. ``enabled`` is how a create page says there is nothing to
   *  fetch yet: it renders the same form as the edit page, and the id it
   *  would ask for does not exist. */
  function single(id: () => string, o: { enabled?: () => boolean } = {}) {
    return apiQuery<TSingle>(
      () => [resource, "single", id()],
      () => `${base}/${id()}`,
      { enabled: o.enabled },
    );
  }

  const create = () =>
    mutation((payload: TCreate) => post<TSingle>(base, payload), { invalidate: [[resource]] });
  const update = () =>
    mutation((vars: { id: string; payload: TUpdate }) => put<TSingle>(`${base}/${vars.id}`, vars.payload), {
      invalidate: [[resource]],
    });
  const archive = () =>
    mutation((id: string) => post<TSingle>(`${base}/${id}/archive`), { invalidate: [[resource]] });
  const restore = () =>
    mutation((id: string) => post<TSingle>(`${base}/${id}/restore`), { invalidate: [[resource]] });
  const remove = () =>
    mutation((id: string) => del<void>(`${base}/${id}`), { invalidate: [[resource]] });

  return { invalidateLists, list, archived, single, create, update, archive, restore, remove };
}
