<script lang="ts">
import EntityListPage from "@/components/EntityListPage.svelte";
import { entityList } from "@/composables/useEntityList.svelte";
import { type RosterListOut, rosters } from "@/composables/useChores.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { t } from "@/i18n.svelte";
import { get } from "@/api/client";
import { choreQrUrl, publicChoreUrl } from "@/lib/chore-urls";
import { queryClient } from "@/lib/query-client";
import { auth } from "@/stores/auth.svelte";

const copy = (key: string, params?: Record<string, unknown>) => t(`chore.list.${key}`, params);
const archive = rosters.archive();
const list = entityList<RosterListOut>({ archive: archive.run, copy });
const query = rosters.list({
  enabled: () => auth.isApproved,
  chapterId: () => list.chapter.value,
});
const share = shareClipboard({
  publicUrlFor: publicChoreUrl,
  qrUrlFor: choreQrUrl,
  copyPrefix: "chore.share",
});

/** Newest first: a roster is made once and then lived in, so the one
 *  just created is the one being set up. */
const sorted = $derived(
  [...(query.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
);

function summary(r: RosterListOut): string {
  const cadence =
    r.period_weeks <= 1
      ? t("chore.recurrence.weekly")
      : t("chore.recurrence.everyKWeeks", { k: r.period_weeks });
  return `${cadence} · ${t("chore.list.choreCount", { n: r.chore_count })}`;
}
</script>

<EntityListPage
  {copy}
  {list}
  items={sorted}
  loaded={!auth.isApproved || !query.isPending}
  isError={query.isError}
  newPath="/chore/new"
  newLabel={copy("newRoster")}
  detailsPath={(r) => `/chore/${r.id}/details`}
  publicUrl={(r) => publicChoreUrl(r.slug)}
  qrSrc={(r) => choreQrUrl(r.slug)}
  sharePrefix="chore.share"
  copyLink={(r) => void share.copyLink(r.slug)}
  copyQr={(r) => void share.copyQr(r.slug)}
  prefetch={(id) =>
    void queryClient.prefetchQuery({
      queryKey: ["chore", "single", id],
      queryFn: () => get(`/api/v1/chore/${id}`),
    })}
>
  {#snippet meta(r: RosterListOut)}
    <p class="muted">{summary(r)}</p>
  {/snippet}
  {#snippet count(r: RosterListOut)}
    {t("chore.list.volunteerCount", { n: r.volunteer_count })}
  {/snippet}
</EntityListPage>
