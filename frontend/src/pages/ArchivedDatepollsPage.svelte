<script lang="ts">
import ArchivedListPage from "@/components/ArchivedListPage.svelte";
import { archivedList } from "@/composables/useArchivedList.svelte";
import { datepolls, type DatepollListOut } from "@/composables/useDatepolls.svelte";
import { t } from "@/i18n.svelte";

const restore = datepolls.restore();
const remove = datepolls.remove();
const list = archivedList<DatepollListOut>({
  restore: restore.run,
  remove: remove.run,
  prefix: "datepoll.archived",
});
const query = datepolls.archived({ chapterId: () => list.chapter.value });
</script>

<ArchivedListPage
  copy={(key: string) => t(`datepoll.archived.${key}`)}
  items={query.data ?? []}
  loaded={!query.isPending}
  {list}
/>
