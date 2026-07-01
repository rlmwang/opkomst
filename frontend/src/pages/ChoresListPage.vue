<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import ListPageView from "@/components/ListPageView.vue";
import { get } from "@/api/client";
import { useChapterUrlFilter } from "@/composables/useChapterUrlFilter";
import {
  type RosterListOut,
  rosterList,
  useArchiveRoster,
  useRosterList,
} from "@/composables/useChores";
import { useChoresClipboard } from "@/composables/useChoresClipboard";
import { useConfirms } from "@/lib/confirms";
import { publicChoreUrl } from "@/lib/chore-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const qc = useQueryClient();
const { copyLink } = useChoresClipboard();

const { chapterFilter, setChapterFilter, chapterOptions } = useChapterUrlFilter();

const rostersQuery = useRosterList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const rosters = rosterList(rostersQuery);
const archiveMutation = useArchiveRoster();

const noChapters = computed(
  () => auth.isApproved && (auth.user?.chapters?.length ?? 0) === 0,
);

watch(rostersQuery.isError, (isError) => {
  if (isError) toasts.error(t("chores.list.loadFailed"));
});

const loaded = computed(() => !auth.isApproved || !rostersQuery.isPending.value);

const sortedRosters = computed(() =>
  [...rosters.value].sort((a, b) => b.created_at.localeCompare(a.created_at)),
);

function summary(r: RosterListOut): string {
  const cadence =
    r.period_weeks <= 1
      ? t("chores.recurrence.weekly")
      : t("chores.recurrence.everyKWeeks", { k: r.period_weeks });
  const chores = t("chores.list.choreCount", { n: r.chore_count });
  const vols = t("chores.list.volunteerCount", { n: r.volunteer_count });
  return `${cadence} · ${chores} · ${vols}`;
}

const prefetched = new Set<string>();
function prefetchDetails(rosterId: string) {
  if (prefetched.has(rosterId)) return;
  prefetched.add(rosterId);
  void qc.prefetchQuery({
    queryKey: ["chores", "single", rosterId],
    queryFn: () => get(`/api/v1/chores/${rosterId}`),
  });
}

function askArchive(r: RosterListOut) {
  confirms.ask({
    header: t("chores.list.archiveConfirmTitle"),
    message: t("chores.list.archiveConfirmBody", { name: r.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("chores.list.archive"),
    accept: async () => {
      try {
        await archiveMutation.mutateAsync(r.id);
        toasts.success(t("chores.list.archived"));
      } catch {
        toasts.error(t("chores.list.archiveFail"));
      }
    },
  });
}
</script>

<template>
  <template v-if="!auth.isApproved">
    <AppHeader />
    <div class="container stack">
      <h1>{{ t("chores.list.title") }}</h1>
      <p class="muted">{{ t("chores.list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.pendingTitle") }}</h2>
        <p>{{ t("dashboard.pendingBody") }}</p>
      </AppCard>
    </div>
  </template>

  <template v-else-if="noChapters">
    <AppHeader />
    <div class="container stack">
      <h1>{{ t("chores.list.title") }}</h1>
      <p class="muted">{{ t("chores.list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.noChaptersTitle") }}</h2>
        <p class="muted">{{ t("dashboard.noChaptersBody") }}</p>
      </AppCard>
    </div>
  </template>

  <ListPageView
    v-else
    :title="t('chores.list.title')"
    :intro="t('chores.list.intro')"
    :items="sortedRosters"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('chores.list.searchPlaceholder')"
    :search-keys="(r: RosterListOut) => [r.name]"
    :empty-copy="t('chores.list.empty')"
    :no-matches-copy="t('chores.list.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #actions-leading>
      <router-link
        :to="{
          path: '/chores/new',
          query: chapterFilter ? { chapter: chapterFilter } : undefined,
        }"
      >
        <Button :label="t('chores.list.newRoster')" icon="pi pi-plus" />
      </router-link>
    </template>

    <template #row="{ item: r }">
      <AppCard
        :stack="false"
        class="roster-card"
        @mouseenter="prefetchDetails(r.id)"
        @focusin="prefetchDetails(r.id)"
      >
        <div class="roster-summary">
          <h3>
            {{ r.name }}
            <span v-if="r.chapter_name" class="chapter-chip">{{ r.chapter_name }}</span>
          </h3>
          <p class="muted summary-line">{{ summary(r) }}</p>
          <div class="link-row">
            <a :href="publicChoreUrl(r.slug)" target="_blank" rel="noopener">{{ publicChoreUrl(r.slug) }}</a>
            <Button
              icon="pi pi-copy"
              size="small"
              severity="secondary"
              text
              v-tooltip.top="t('chores.share.copyLink')"
              :aria-label="t('chores.share.copyLink')"
              @click="copyLink(r.slug)"
            />
          </div>
        </div>

        <div class="actions">
          <router-link :to="`/chores/${r.id}/details`">
            <Button :label="t('chores.list.details')" icon="pi pi-info-circle" size="small" severity="secondary" />
          </router-link>
          <Button
            :label="t('chores.list.archive')"
            icon="pi pi-archive"
            size="small"
            severity="secondary"
            text
            @click="askArchive(r)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>

<style scoped>
.roster-card {
  display: flex;
  justify-content: space-between;
  gap: 1.25rem;
  align-items: stretch;
  flex-wrap: wrap;
}
.roster-summary {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}
.roster-summary h3 { margin: 0 0 0.25rem; }
.summary-line { margin: 0 0 0.25rem; font-size: 0.875rem; }
.chapter-chip {
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
  align-items: center;
}
</style>
