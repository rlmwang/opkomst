import { del, post, put } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import type { Page } from "@/api/types";
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
 * Query keys: ``[resource, "active", {chapter, page, q}]``,
 * ``[resource, "archived", {chapter, page, q}]``, ``[resource,
 * "single", id]``.
 */
export function createEntityCrud<TList, TSingle, TCreate, TUpdate = TCreate>(opts: {
  resource: string;
}) {
  const { resource } = opts;
  const base = `/api/v1/${resource}`;
  const invalidateLists = () => void queryClient.invalidateQueries({ queryKey: [resource] });

  /** What the server needs to answer with one page: the chapter, the
   *  page number and the search box. Everything the list is looking at
   *  is in the query key, so narrowing it is a fresh cache entry and
   *  going back is not a request. */
  type Window = {
    enabled?: () => boolean;
    chapterId?: () => string | null;
    page?: () => number;
    search?: () => string;
  };

  function where(o: Window) {
    return { chapter: o.chapterId?.() ?? null, page: o.page?.() ?? 1, q: o.search?.() ?? "" };
  }

  function url(path: string, o: Window) {
    const params = new URLSearchParams();
    const chapter = o.chapterId?.();
    if (chapter) params.set("chapter_id", chapter);
    const page = o.page?.() ?? 1;
    if (page > 1) params.set("page", String(page));
    const q = o.search?.().trim();
    if (q) params.set("q", q);
    const query = params.toString();
    return query ? `${path}?${query}` : path;
  }

  /** Active list, chapter-scoped. A null chapter is every chapter the
   *  user belongs to. */
  function list(o: Window = {}) {
    return apiQuery<Page<TList>>(
      () => [resource, "active", where(o)],
      () => url(base, o),
      { enabled: o.enabled },
    );
  }

  function archived(o: Window = {}) {
    return apiQuery<Page<TList>>(
      () => [resource, "archived", where(o)],
      () => url(`${base}/archived`, o),
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
