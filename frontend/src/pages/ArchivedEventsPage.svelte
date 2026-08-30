<script lang="ts">
import ArchivedListPage from "@/components/ArchivedListPage.svelte";
import { archivedList } from "@/composables/useArchivedList.svelte";
import { deleteEvent, events, type EventListOut } from "@/composables/useEvents.svelte";
import { locale, t } from "@/i18n.svelte";
import { formatDateTime } from "@/lib/format";
import { recurrenceHint } from "@/lib/recurrence";

/** The archived events. The only resource whose rows say more than
 *  their name: when it ran, where, and how it repeated. */
const restore = events.restore();
const remove = deleteEvent();
const list = archivedList<EventListOut>({
  restore: restore.run,
  remove: remove.run,
  prefix: "archived",
});
const query = events.archived({
  chapterId: () => list.chapter.value,
  page: () => list.chapter.page,
  search: () => list.chapter.search,
});
</script>

<ArchivedListPage
  copy={(key: string) => t(`archived.${key}`)}
  items={query.data?.items ?? []}
  total={query.data?.total ?? 0}
  perPage={query.data?.per_page ?? 0}
  loaded={!query.isPending}
  {list}
>
  {#snippet meta(e: EventListOut)}
    <p class="muted">
      {#if e.location}{e.location} · {/if}
      {formatDateTime(e.next_starts_at ?? `${e.starts_on}T${e.start_time}`, locale())} ·
      {recurrenceHint(t, e)}
    </p>
  {/snippet}
</ArchivedListPage>
