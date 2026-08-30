<script lang="ts">
import EntityListPage from "@/components/EntityListPage.svelte";
import { entityList } from "@/composables/useEntityList.svelte";
import { datepolls, type DatepollListOut } from "@/composables/useDatepolls.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { locale, t } from "@/i18n.svelte";
import { get } from "@/api/client";
import { datepollQrUrl, publicDatepollUrl } from "@/lib/datepoll-urls";
import { formatDate } from "@/lib/format";
import { queryClient } from "@/lib/query-client";
import { auth } from "@/stores/auth.svelte";

const copy = (key: string, params?: Record<string, unknown>) => t(`datepoll.list.${key}`, params);
const archive = datepolls.archive();
const list = entityList<DatepollListOut>({ archive: archive.run, copy });
const query = datepolls.list({
  enabled: () => auth.isApproved,
  chapterId: () => list.chapter.value,
});
const share = shareClipboard({
  publicUrlFor: publicDatepollUrl,
  qrUrlFor: datepollQrUrl,
  copyPrefix: "datepoll.share",
});

// Newest first is the statement's order, and the list arrives one page
// at a time.
const page = $derived(query.data ?? null);

/** How many dates are on offer and when they run. A poll with one date
 *  says that date; a poll with none says so, because it is a poll that
 *  cannot be answered yet. */
function dateRange(p: DatepollListOut): string {
  if (p.date_count === 0) return t("datepoll.list.noDates");
  const count = t("datepoll.list.dateCount", { n: p.date_count });
  if (!p.first_date) return count;
  const first = formatDate(p.first_date, locale());
  if (!p.last_date || p.last_date === p.first_date) return `${count} · ${first}`;
  return `${count} · ${first} – ${formatDate(p.last_date, locale())}`;
}
</script>

<EntityListPage
  {copy}
  {list}
  items={page?.items ?? []}
  total={page?.total ?? 0}
  perPage={page?.per_page ?? 0}
  loaded={!auth.isApproved || !query.isPending}
  isError={query.isError}
  newPath="/datepoll/new"
  newLabel={copy("newDatepoll")}
  detailsPath={(p) => `/datepoll/${p.id}/details`}
  publicUrl={(p) => publicDatepollUrl(p.slug)}
  qrSrc={(p) => datepollQrUrl(p.slug)}
  sharePrefix="datepoll.share"
  copyLink={(p) => void share.copyLink(p.slug)}
  copyQr={(p) => void share.copyQr(p.slug)}
  prefetch={(id) => {
    void queryClient.prefetchQuery({
      queryKey: ["datepoll", "single", id],
      queryFn: () => get(`/api/v1/datepoll/${id}`),
    });
    void queryClient.prefetchQuery({
      queryKey: ["datepoll", id, "summary"],
      queryFn: () => get(`/api/v1/datepoll/${id}/summary`),
    });
  }}
>
  {#snippet meta(p: DatepollListOut)}
    <p class="muted">{dateRange(p)}</p>
  {/snippet}
  {#snippet count(p: DatepollListOut)}
    {t("datepoll.list.responseCount", { n: p.submission_count })}
  {/snippet}
</EntityListPage>
