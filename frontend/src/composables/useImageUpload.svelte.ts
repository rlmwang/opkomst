import { del, postFile } from "@/api/client";
import { queryClient } from "@/lib/query-client";

/**
 * Hero-image upload and delete for any chapter-scoped resource that has
 * an ``image_url`` (events, forms, datepolls). One implementation behind
 * the three ``POST/DELETE /api/v1/{resource}/{id}/image`` endpoints; the
 * server returns the fresh row, which is patched into every relevant
 * cache so the new ``image_url`` shows without a refetch.
 *
 * Plain async functions rather than mutations, because the only thing a
 * mutation was adding here is a pending flag, and the one component
 * that calls these already keeps its own.
 */

/** Minimal shape the cache patch needs. The endpoint returns the full
 *  DTO at runtime; this is just what the module reads. */
interface ImageEntity {
  id: string;
  slug: string;
  image_url: string | null;
}

export function useImageUpload(resource: string) {
  const patch = (entity: ImageEntity) => {
    // List caches (``[resource, "active"|"archived", …]``) hold arrays.
    queryClient.setQueriesData<ImageEntity[]>({ queryKey: [resource] }, (old) =>
      Array.isArray(old) ? old.map((e) => (e.id === entity.id ? entity : e)) : old,
    );
    // Single and public-by-slug caches.
    queryClient.setQueryData([resource, "single", entity.id], entity);
    queryClient.setQueryData([resource, "by-slug", entity.slug], entity);
    void queryClient.invalidateQueries({ queryKey: [resource] });
  };

  return {
    async upload(id: string, file: File): Promise<ImageEntity> {
      const entity = await postFile<ImageEntity>(`/api/v1/${resource}/${id}/image`, file);
      patch(entity);
      return entity;
    },
    async remove(id: string): Promise<ImageEntity> {
      const entity = await del<ImageEntity>(`/api/v1/${resource}/${id}/image`);
      patch(entity);
      return entity;
    },
  };
}
