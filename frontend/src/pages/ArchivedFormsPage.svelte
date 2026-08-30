<script lang="ts">
import ArchivedListPage from "@/components/ArchivedListPage.svelte";
import { archivedList } from "@/composables/useArchivedList.svelte";
import { type FormListOut, formsApi } from "@/composables/useForms.svelte";
import { formText } from "@/composables/useFormText.svelte";

/** One page, three products; the route says which. */
const api = formsApi();
const { L } = formText();
const restore = api.restore();
const remove = api.remove();
const list = archivedList<FormListOut>({
  restore: restore.run,
  remove: remove.run,
  prefix: `${api.resource}.archived`,
});
const query = api.archived({ chapterId: () => list.chapter.value });
</script>

<ArchivedListPage
  copy={(key: string) => L(`archived.${key}`)}
  items={query.data ?? []}
  loaded={!query.isPending}
  {list}
/>
