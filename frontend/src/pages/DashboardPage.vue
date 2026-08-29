<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import AppButton from "@/components/AppButton.vue";
import MultiSelectField from "@/components/MultiSelectField.vue";
import { computed, ref, watch } from "vue";
import { useI18n } from "@/i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import EntityCard from "@/components/EntityCard.vue";
import EventMetaLines from "@/components/EventMetaLines.vue";
import ListPageView from "@/components/ListPageView.vue";
import { get } from "@/api/client";
import { useSetUserChapters } from "@/composables/useAdmin";
import { type Chapter, chapterList, useChapters } from "@/composables/useChapters";
import {
  type EventListOut,
  eventList,
  useArchiveEvent,
  useEventList,
} from "@/composables/useEvents";
import { useEventClipboard } from "@/composables/useEventClipboard";
import { useConfirms } from "@/lib/confirms";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";
import { useHoverPrefetch } from "@/composables/useHoverPrefetch";

const { t } = useI18n();
const lt = useLocalizedText();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const router = useRouter();
const route = useRoute();
const { copyLink, copyQr } = useEventClipboard();

// Chapter filter — backed by the ``?chapter=`` URL param so a
// reload or shared link reproduces the view. ``null`` is the
// "all my chapters" sentinel; assigning it strips the param.
const chapterFilter = computed<string | null>(() => {
  const v = route.query.chapter;
  return typeof v === "string" && v ? v : null;
});

function setChapterFilter(value: string | null) {
  void router.replace({
    query: { ...route.query, chapter: value ?? undefined },
  });
}

const eventsQuery = useEventList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const events = eventList(eventsQuery);
const archiveMutation = useArchiveEvent();

// The dropdown options expose the user's *live* chapter
// memberships, not a synthesised "all chapters" list — admins
// included. The "all" sentinel is rendered as a separate
// option, not a member of the array.
const chapterOptions = computed(() => auth.user?.chapters ?? []);

// Onboarding banner state — shown when an approved user has no
// chapter memberships. We let them pick chapters inline and
// commit via /set-chapters; on success the auth store refetches
// so the banner disappears and the events list lights up.
// Only the onboarding banner reads this, so it is fetched only when
// the banner is up. A personal account never has chapters and the
// endpoint 404s for it.
const allChaptersQuery = useChapters({
  includeArchived: false,
  enabled: computed(() => auth.needsChapters),
});
const allChapters = chapterList(allChaptersQuery);
const onboardingPicks = ref<Chapter[]>([]);
const setChaptersMutation = useSetUserChapters();
const onboardingSubmitting = ref(false);
// Forward reference to the query client created below — used by
// the onboarding submit to invalidate the (empty) events query
// it cached while the user had no chapters.
const qc = useQueryClient();

async function submitOnboardingChapters() {
  if (!auth.user || onboardingPicks.value.length === 0) return;
  onboardingSubmitting.value = true;
  try {
    await setChaptersMutation.mutateAsync({
      userId: auth.user.id,
      chapterIds: onboardingPicks.value.map((c) => c.id),
    });
    // Refresh the user store so ``auth.user.chapters`` reflects
    // the new set; the banner is wired off that and disappears
    // as soon as the value lands.
    await auth.fetchMe();
    // The events query already ran (and cached an empty result)
    // while the user had zero chapters. Invalidate so the next
    // render refetches against the new membership set instead
    // of showing the cached empty list.
    await qc.invalidateQueries({ queryKey: ["event"] });
    toasts.success(t("dashboard.noChaptersSavedToast"));
  } catch {
    toasts.error(t("dashboard.noChaptersSaveFailed"));
  } finally {
    onboardingSubmitting.value = false;
  }
}

// Prefetch what EventDetailsPage reads on mount, when an organiser
// hovers a card. By the time the click resolves and the page mounts,
// both queries are already in cache — no skeleton flash. Idempotent:
// prefetchQuery is a no-op when the data is already fresh under the
// default staleTime. The keys are the ones ``useEventOccurrences``
// and ``useFeedbackSummary`` use; a key that doesn't match is a
// request nobody ever reads. The per-day signups and stats are not
// prefetched: they hang off an occurrence id that only exists once
// the occurrence list has landed.
const hover = useHoverPrefetch((eventId: string) => {
  void qc.prefetchQuery({
    queryKey: ["event", eventId, "occurrences"],
    queryFn: () => get(`/api/v1/event/${eventId}/occurrences`),
  });
  void qc.prefetchQuery({
    queryKey: ["feedback", "summary", eventId],
    queryFn: () => get(`/api/v1/event/${eventId}/feedback-summary`),
  });
});

watch(eventsQuery.isError, (isError) => {
  if (isError) toasts.error(t("dashboard.loadFailed"));
});

const loaded = computed(() => !auth.isApproved || !eventsQuery.isPending.value);

// Upcoming first, soonest next session at the top; events whose every
// occurrence is past sink below, most-recent first.
const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => {
    const an = a.next_starts_at;
    const bn = b.next_starts_at;
    if (an && bn) return an.localeCompare(bn);
    if (an) return -1;
    if (bn) return 1;
    return b.starts_on.localeCompare(a.starts_on);
  }),
);

function askArchive(e: EventListOut) {
  confirms.ask({
    header: t("dashboard.archiveConfirmTitle"),
    message: t("dashboard.archiveConfirmBody", { name: lt(e.name_nl, e.name_en) ?? "" }),
    icon: "exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("dashboard.archive"),
    accept: async () => {
      try {
        await archiveMutation.mutateAsync(e.id);
        toasts.success(t("dashboard.archived"));
      } catch {
        toasts.error(t("dashboard.archiveFail"));
      }
    },
  });
}
</script>

<template>
  <!-- Pre-list short-circuits. Both branches render their own
       AppHeader + page-title chrome rather than the shell's,
       because the shell unconditionally renders the
       actions-row + list, which neither state has any business
       showing. -->
  <template v-if="auth.needsChapters">
    <AppHeader />
    <div class="container-wide stack">
      <h1>{{ t("dashboard.title") }}</h1>
      <p class="muted">{{ t("dashboard.intro") }}</p>
      <!-- Approved-but-no-chapter banner. The signup flow doesn't
           ask for a chapter (deliberate — chapter names would
           leak pre-auth). Pick inline so the first-time path is
           one click: select chapters, hit Save, and the banner
           dissolves into a populated events list. -->
      <AppCard>
        <h2>{{ t("dashboard.noChaptersTitle") }}</h2>
        <p class="muted">{{ t("dashboard.noChaptersBody") }}</p>
        <div class="onboarding-picker">
          <MultiSelectField
            v-model="onboardingPicks"
            :options="allChapters"
            option-label="name"
            :placeholder="t('dashboard.noChaptersPlaceholder')"
            display="chip"
            filter
            fluid
          />
          <AppButton
            :label="t('dashboard.noChaptersCta')"
            :disabled="onboardingPicks.length === 0"
            :loading="onboardingSubmitting"
            @click="submitOnboardingChapters"
          />
        </div>
      </AppCard>
    </div>
  </template>

  <ListPageView
    v-else
    :title="t('dashboard.title')"
    :intro="t('dashboard.intro')"
    :items="sortedEvents"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('dashboard.searchPlaceholder')"
    :search-keys="(e: EventListOut) => [lt(e.name_nl, e.name_en) ?? '', e.location ?? '']"
    :empty-copy="t('dashboard.empty')"
    :no-matches-copy="t('dashboard.noMatches')"
    :skeleton-rows="3"
    @update:chapter-filter="setChapterFilter"
  >
    <template #actions-leading>
      <router-link
        :to="{
          path: '/event/new',
          query: chapterFilter ? { chapter: chapterFilter } : undefined,
        }"
      >
        <AppButton :label="t('dashboard.newEvent')" icon="plus" />
      </router-link>
    </template>

    <template #row="{ item: e }">
      <!-- The stub links the first upcoming occurrence (falling back to
           the most recent past one), matching the other entity cards. -->
      <EntityCard
        :public-url="e.next_slug ? publicEventUrl(e.next_slug) : undefined"
        :qr-src="e.next_slug ? eventQrUrl(e.next_slug) : undefined"
        :copy-link-label="t('event.share.copyLink')"
        :qr-label="t('event.share.copyQr')"
        @mouseenter="hover.enter(e.id)"
        @mouseleave="hover.leave()"
        @focusin="hover.enter(e.id)"
        @copy-link="e.next_slug && copyLink(e.next_slug)"
        @copy-qr="e.next_slug && copyQr(e.next_slug)"
      >
        <template #title>
          <h3>
            {{ lt(e.name_nl, e.name_en) }}
            <span v-if="e.chapter_name" class="chapter-chip">{{ e.chapter_name }}</span>
          </h3>
        </template>

        <template #meta>
          <EventMetaLines :event="e" />
        </template>

        <template #actions>
          <router-link :to="`/event/${e.id}/details`">
            <AppButton :label="t('dashboard.details')" icon="info-circle" size="small" severity="secondary" />
          </router-link>
          <AppButton
            :label="t('dashboard.archive')"
            icon="archive"
            size="small"
            severity="secondary"
            text
            @click="askArchive(e)"
          />
        </template>

        <template #count>{{ t("dashboard.attendeeCount", { n: e.attendee_count }) }}</template>
      </EntityCard>
    </template>
  </ListPageView>
</template>

<style scoped>
.onboarding-picker {
  display: flex;
  gap: 0.75rem;
  align-items: stretch;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
.onboarding-picker :deep(.p-multiselect) {
  flex: 1;
  min-width: 0;
}
</style>
