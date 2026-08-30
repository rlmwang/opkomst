<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import EntityListPage from "@/components/EntityListPage.svelte";
import EventMetaLines from "@/components/EventMetaLines.svelte";
import MultiSelectField from "@/components/MultiSelectField.svelte";
import { setUserChapters } from "@/composables/useAdmin.svelte";
import { type Chapter, chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import { entityList } from "@/composables/useEntityList.svelte";
import { archiveEvent, type EventListOut, events } from "@/composables/useEvents.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { t } from "@/i18n.svelte";
import { get } from "@/api/client";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { queryClient } from "@/lib/query-client";
import { useToasts } from "@/lib/toasts";
import { auth, fetchMe } from "@/stores/auth.svelte";

/** The organiser's home: their chapters' events, soonest first. */
const copy = (key: string, params?: Record<string, unknown>) => t(`dashboard.${key}`, params);
const toasts = useToasts();
const archive = archiveEvent();
const list = entityList<EventListOut>({ archive: archive.run, copy });
const query = events.list({ enabled: () => auth.isApproved, chapterId: () => list.chapter.value });
const share = shareClipboard({
  publicUrlFor: publicEventUrl,
  qrUrlFor: eventQrUrl,
  copyPrefix: "event.share",
});

// Upcoming first, soonest next session at the top; an event whose every
// occurrence is past sinks below, most recent first.
const sorted = $derived(
  [...(query.data ?? [])].sort((a, b) => {
    const an = a.next_starts_at;
    const bn = b.next_starts_at;
    if (an && bn) return an.localeCompare(bn);
    if (an) return -1;
    if (bn) return 1;
    return b.starts_on.localeCompare(a.starts_on);
  }),
);

// The onboarding picker. Signing up never asks for a chapter, because
// chapter names would leak before the account exists, so an approved
// organiser can arrive belonging to nothing. Picking here is one click
// from a banner to a populated list. The chapter list is fetched only
// while the banner is up: a personal account has no chapters and the
// endpoint 404s for it.
const allChapters = chaptersQuery({ enabled: () => auth.needsChapters });
const setChapters = setUserChapters();
let picks = $state<Chapter[]>([]);

async function submitOnboardingChapters(): Promise<void> {
  if (!auth.user || picks.length === 0) return;
  try {
    await setChapters.run({ userId: auth.user.id, chapterIds: picks.map((c) => c.id) });
    // The store drives the banner, so it has to hear about the new
    // memberships before the banner can go away. The events query
    // already ran and cached an empty list against no chapters at all,
    // so it is thrown away rather than shown again.
    await fetchMe();
    await queryClient.invalidateQueries({ queryKey: ["event"] });
    toasts.success(t("dashboard.noChaptersSavedToast"));
  } catch {
    toasts.error(t("dashboard.noChaptersSaveFailed"));
  }
}
</script>

<EntityListPage
  {copy}
  {list}
  items={sorted}
  loaded={!auth.isApproved || !query.isPending}
  isError={query.isError}
  newPath="/event/new"
  newLabel={copy("newEvent")}
  detailsPath={(e) => `/event/${e.id}/details`}
  publicUrl={(e) => (e.next_slug ? publicEventUrl(e.next_slug) : undefined)}
  qrSrc={(e) => (e.next_slug ? eventQrUrl(e.next_slug) : undefined)}
  sharePrefix="event.share"
  copyLink={(e) => e.next_slug && void share.copyLink(e.next_slug)}
  copyQr={(e) => e.next_slug && void share.copyQr(e.next_slug)}
  searchKeys={(e) => [lt(e.name_nl, e.name_en) ?? "", e.location ?? ""]}
  prefetch={(id) => {
    // What the details page reads on mount, which is one request now,
    // so the click lands on a painted page.
    void queryClient.prefetchQuery({
      queryKey: ["event", id, "page"],
      queryFn: () => get(`/api/v1/event/${id}/page`),
    });
  }}
>
  {#snippet meta(e: EventListOut)}
    <EventMetaLines event={e} />
  {/snippet}
  {#snippet count(e: EventListOut)}
    {t("dashboard.attendeeCount", { n: e.attendee_count })}
  {/snippet}
  {#snippet onboarding()}
    <div class="onboarding-picker">
      <MultiSelectField
        bind:value={picks}
        options={sortedChapters(allChapters.data)}
        optionLabel="name"
        placeholder={t("dashboard.noChaptersPlaceholder")}
        display="chip"
        filter
        fluid
      />
      <AppButton
        label={t("dashboard.noChaptersCta")}
        disabled={picks.length === 0}
        loading={setChapters.pending}
        onclick={submitOnboardingChapters}
      />
    </div>
  {/snippet}
</EntityListPage>

<style>
.onboarding-picker {
  display: flex;
  gap: 0.75rem;
  align-items: stretch;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
.onboarding-picker :global(.ms-field) {
  flex: 1;
  min-width: 0;
}
</style>
