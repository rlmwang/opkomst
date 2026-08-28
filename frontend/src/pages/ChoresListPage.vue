<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import EntityCard from "@/components/EntityCard.vue";
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
import { choreQrUrl, publicChoreUrl } from "@/lib/chore-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const lt = useLocalizedText();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const qc = useQueryClient();
const { copyLink, copyQr } = useChoresClipboard();

const { chapterFilter, setChapterFilter, chapterOptions } = useChapterUrlFilter();

const rostersQuery = useRosterList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const rosters = rosterList(rostersQuery);
const archiveMutation = useArchiveRoster();


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
  return `${cadence} · ${chores}`;
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
    message: t("chores.list.archiveConfirmBody", { name: lt(r.name_nl, r.name_en) ?? "" }),
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
  <template v-if="auth.needsChapters">
    <AppHeader />
    <div class="container-wide stack">
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
    :search-keys="(r: RosterListOut) => [lt(r.name_nl, r.name_en) ?? '']"
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
      <EntityCard
        :public-url="publicChoreUrl(r.slug)"
        :qr-src="choreQrUrl(r.slug)"
        :copy-link-label="t('chores.share.copyLink')"
        :qr-label="t('chores.share.copyQr')"
        @mouseenter="prefetchDetails(r.id)"
        @focusin="prefetchDetails(r.id)"
        @copy-link="copyLink(r.slug)"
        @copy-qr="copyQr(r.slug)"
      >
        <template #title>
          <h3>
            {{ lt(r.name_nl, r.name_en) }}
            <span v-if="r.chapter_name" class="chapter-chip">{{ r.chapter_name }}</span>
          </h3>
        </template>

        <template #meta>
          <p class="muted">{{ summary(r) }}</p>
        </template>


        <template #actions>
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
        </template>

        <template #count>{{ t("chores.list.volunteerCount", { n: r.volunteer_count }) }}</template>
      </EntityCard>
    </template>
  </ListPageView>
</template>
