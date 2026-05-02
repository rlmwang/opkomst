<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import Button from "primevue/button";
import MultiSelect from "primevue/multiselect";
import Select from "primevue/select";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";
import { get } from "@/api/client";
import { useSetUserChapters } from "@/composables/useAdmin";
import { type Chapter, chapterList, useChapters } from "@/composables/useChapters";
import { useEventClipboard } from "@/composables/useEventClipboard";
import {
  type EventOut,
  eventList,
  useArchiveEvent,
  useEventList,
} from "@/composables/useEvents";
import { useConfirms } from "@/lib/confirms";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { formatDateTime } from "@/lib/format";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t, locale } = useI18n();
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
const noChapters = computed(
  () => auth.isApproved && (auth.user?.chapters?.length ?? 0) === 0,
);
const allChaptersQuery = useChapters({ includeArchived: false });
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
    await qc.invalidateQueries({ queryKey: ["events"] });
    toasts.success(t("dashboard.noChaptersSavedToast"));
  } catch {
    toasts.error(t("dashboard.noChaptersSaveFailed"));
  } finally {
    onboardingSubmitting.value = false;
  }
}

// Prefetch the per-event reads (stats / signups / feedback-summary)
// when an organiser hovers a card. By the time the click resolves
// and EventDetailsPage mounts, those queries are already in cache
// — no skeleton flash. Idempotent: prefetchQuery is a no-op when
// the data is already fresh under the default staleTime.
const prefetched = new Set<string>();
function prefetchDetails(eventId: string) {
  if (prefetched.has(eventId)) return;
  prefetched.add(eventId);
  void qc.prefetchQuery({
    queryKey: ["events", eventId, "stats"],
    queryFn: () => get(`/api/v1/events/${eventId}/stats`),
  });
  void qc.prefetchQuery({
    queryKey: ["events", eventId, "signups"],
    queryFn: () => get(`/api/v1/events/${eventId}/signups`),
  });
  void qc.prefetchQuery({
    queryKey: ["feedback", "summary", eventId],
    queryFn: () => get(`/api/v1/events/${eventId}/feedback-summary`),
  });
}

watch(eventsQuery.isError, (isError) => {
  if (isError) toasts.error(t("dashboard.loadFailed"));
});

const query = ref("");
const loaded = computed(() => !auth.isApproved || !eventsQuery.isPending.value);

const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => b.starts_at.localeCompare(a.starts_at)),
);

const filteredEvents = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return sortedEvents.value;
  return sortedEvents.value.filter(
    (e) => e.name.toLowerCase().includes(q) || e.location.toLowerCase().includes(q),
  );
});

function askArchive(e: EventOut) {
  confirms.ask({
    header: t("dashboard.archiveConfirmTitle"),
    message: t("dashboard.archiveConfirmBody", { name: e.name }),
    icon: "pi pi-exclamation-triangle",
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
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("dashboard.title") }}</h1>
    <p class="muted">{{ t("dashboard.intro") }}</p>

    <AppCard v-if="!auth.isApproved">
      <h2>{{ t("dashboard.pendingTitle") }}</h2>
      <p>{{ t("dashboard.pendingBody") }}</p>
    </AppCard>

    <!-- Approved-but-no-chapter banner. The signup flow doesn't
         ask for a chapter (deliberate — chapter names would
         leak pre-auth). Pick inline so the first-time path is
         one click: select chapters, hit Save, and the banner
         dissolves into a populated events list. -->
    <AppCard v-else-if="noChapters">
      <h2>{{ t("dashboard.noChaptersTitle") }}</h2>
      <p class="muted">{{ t("dashboard.noChaptersBody") }}</p>
      <div class="onboarding-picker">
        <MultiSelect
          v-model="onboardingPicks"
          :options="allChapters"
          option-label="name"
          :placeholder="t('dashboard.noChaptersPlaceholder')"
          display="chip"
          filter
          fluid
        />
        <Button
          :label="t('dashboard.noChaptersCta')"
          :disabled="onboardingPicks.length === 0"
          :loading="onboardingSubmitting"
          @click="submitOnboardingChapters"
        />
      </div>
    </AppCard>

    <template v-else>
      <div class="actions-row">
        <router-link
          :to="{
            path: '/events/new',
            query: chapterFilter ? { chapter: chapterFilter } : undefined,
          }"
        >
          <Button :label="t('dashboard.newEvent')" icon="pi pi-plus" />
        </router-link>
        <Select
          :model-value="chapterFilter"
          :options="[{ id: null, name: t('dashboard.chapterFilterAll') }, ...chapterOptions]"
          option-label="name"
          option-value="id"
          :placeholder="t('dashboard.chapterFilterAll')"
          class="chapter-filter"
          @update:model-value="setChapterFilter"
        />
        <SearchInput
          v-model="query"
          :placeholder="t('dashboard.searchPlaceholder')"
          class="search"
        />
      </div>

      <AppSkeleton v-if="!loaded" :rows="3" cards />

      <AppCard v-else-if="sortedEvents.length === 0" :stack="false">
        <p class="muted">{{ t("dashboard.empty") }}</p>
      </AppCard>

      <p v-else-if="filteredEvents.length === 0" class="muted">
        {{ t("dashboard.noMatches") }}
      </p>

      <AppCard
        v-for="e in filteredEvents"
        :key="e.id"
        :stack="false"
        class="event-card"
        @mouseenter="prefetchDetails(e.id)"
        @focusin="prefetchDetails(e.id)"
      >
        <div class="event-main">
          <div class="event-summary">
            <h3>
              {{ e.name }}
              <span v-if="e.chapter_name" class="event-chapter-chip">{{ e.chapter_name }}</span>
            </h3>
            <p class="muted">
              {{ e.location }} · {{ formatDateTime(e.starts_at, locale) }}
            </p>
            <div class="link-row">
              <a :href="publicEventUrl(e.slug)" target="_blank" rel="noopener">{{ publicEventUrl(e.slug) }}</a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                :aria-label="t('event.share.copyLink')"
                @click="copyLink(e.slug)"
              />
            </div>
          </div>

          <div class="actions">
            <router-link :to="`/events/${e.id}/details`">
              <Button :label="t('dashboard.details')" icon="pi pi-info-circle" size="small" severity="secondary" />
            </router-link>
            <Button
              :label="t('dashboard.archive')"
              icon="pi pi-archive"
              size="small"
              severity="secondary"
              text
              @click="askArchive(e)"
            />
          </div>
        </div>

        <div class="event-side">
          <div class="muted attendee-count">{{ t("dashboard.attendeeCount", { n: e.attendee_count }) }}</div>
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('event.share.copyQr')"
            :aria-label="t('event.share.copyQr')"
            @click="copyQr(e.slug)"
          >
            <img :src="eventQrUrl(e.slug)" alt="" class="qr" />
          </button>
        </div>
      </AppCard>
    </template>
  </div>
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
.actions-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.actions-row .search {
  flex: 1;
  max-width: 24rem;
  margin-left: auto;
}
.event-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.25rem;
  align-items: stretch;
}
.event-main {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  min-width: 0;
}
.event-summary h3 { margin: 0 0 0.25rem; }
.event-summary > .muted { margin: 0; }
.event-summary .link-row { margin-top: 0.25rem; }
.event-chapter-chip {
  display: inline-flex;
  align-items: center;
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.75rem;
  white-space: nowrap;
  vertical-align: baseline;
}
.chapter-filter {
  min-width: 12rem;
}

.event-side {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  gap: 0.5rem;
}
.attendee-count { white-space: nowrap; }

.link-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
}
.link-row a {
  font-size: 0.9375rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.actions {
  display: flex;
  gap: 0.5rem;
  margin-top: auto;
}

.qr-button {
  align-self: center;
  line-height: 0;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  border-radius: 6px;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.qr-button:hover {
  transform: scale(1.03);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 4px;
  display: block;
}

@media (max-width: 540px) {
  .event-card {
    grid-template-columns: 1fr;
  }
  /* Mobile event-side: cluster the count next to the QR at the
   * right edge instead of pushing them to opposite edges with
   * ``space-between`` (which left a big awkward gap and read as
   * "these two things accidentally landed here"). Right-aligned
   * cluster reads as "the per-event sidebar moved to the bottom",
   * which is the actual intent. */
  .event-side {
    flex-direction: row;
    justify-content: flex-end;
    align-items: center;
    gap: 0.75rem;
  }
}
</style>
