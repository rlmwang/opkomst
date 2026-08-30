<script lang="ts">
import ArchivedListPage from "@/components/ArchivedListPage.svelte";
import { archivedList } from "@/composables/useArchivedList.svelte";
import { type RosterListOut, rosters } from "@/composables/useChores.svelte";
import { t } from "@/i18n.svelte";

const restore = rosters.restore();
const remove = rosters.remove();
const list = archivedList<RosterListOut>({
  restore: restore.run,
  remove: remove.run,
  prefix: "chore.archived",
});
const query = rosters.archived({
  chapterId: () => list.chapter.value,
  page: () => list.chapter.page,
  search: () => list.chapter.search,
});
</script>

<ArchivedListPage
  copy={(key: string) => t(`chore.archived.${key}`)}
  items={query.data?.items ?? []}
  total={query.data?.total ?? 0}
  perPage={query.data?.per_page ?? 0}
  loaded={!query.isPending}
  {list}
/>
