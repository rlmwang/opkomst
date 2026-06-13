/**
 * Hero-image upload/delete for any chapter-scoped resource that has
 * an ``image_url`` (events, forms, datepolls). One implementation
 * behind the three ``POST/DELETE /api/v1/{resource}/{id}/image``
 * endpoints; the server returns the fresh row, which we patch into
 * every relevant cache so the new ``image_url`` shows without a
 * refetch. Mirrors the old event-only hooks, generalised.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";

import { del, postFile } from "@/api/client";

/** Minimal shape the cache-patch needs. The endpoint returns the full
 *  DTO at runtime; this is just what the composable reads. */
interface ImageEntity {
  id: string;
  slug: string;
  image_url: string | null;
}

export function useImageUpload(resource: string) {
  const qc = useQueryClient();

  const patch = (entity: ImageEntity) => {
    // List caches (``[resource, "active"|"archived", …]``) hold arrays.
    qc.setQueriesData<ImageEntity[]>({ queryKey: [resource] }, (old) =>
      Array.isArray(old) ? old.map((e) => (e.id === entity.id ? entity : e)) : old,
    );
    // Single + public-by-slug caches.
    qc.setQueryData([resource, "single", entity.id], entity);
    qc.setQueryData([resource, "by-slug", entity.slug], entity);
  };
  const invalidate = () => qc.invalidateQueries({ queryKey: [resource] });

  const upload = useMutation({
    mutationFn: (vars: { id: string; file: File }) =>
      postFile<ImageEntity>(`/api/v1/${resource}/${vars.id}/image`, vars.file),
    onSuccess: patch,
    onSettled: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => del<ImageEntity>(`/api/v1/${resource}/${id}/image`),
    onSuccess: patch,
    onSettled: invalidate,
  });

  return { upload, remove };
}
