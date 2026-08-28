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
import { useDatepollClipboard } from "@/composables/useDatepollClipboard";
import {
  type DatepollListOut,
  datepollList,
  useArchiveDatepoll,
  useDatepollList,
} from "@/composables/useDatepolls";
import { useConfirms } from "@/lib/confirms";
import { datepollQrUrl, publicDatepollUrl } from "@/lib/datepoll-urls";
import { formatDate } from "@/lib/format";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t, locale } = useI18n();
const lt = useLocalizedText();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const qc = useQueryClient();
const { copyLink, copyQr } = useDatepollClipboard();

const { chapterFilter, setChapterFilter, chapterOptions } = useChapterUrlFilter();

const pollsQuery = useDatepollList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const polls = datepollList(pollsQuery);
const archiveMutation = useArchiveDatepoll();


watch(pollsQuery.isError, (isError) => {
  if (isError) toasts.error(t("datepolls.list.loadFailed"));
});

const loaded = computed(() => !auth.isApproved || !pollsQuery.isPending.value);

const sortedPolls = computed(() =>
  [...polls.value].sort((a, b) => b.created_at.localeCompare(a.created_at)),
);

function dateRange(p: DatepollListOut): string {
  if (p.date_count === 0) return t("datepolls.list.noDates");
  const count = t("datepolls.list.dateCount", { n: p.date_count });
  if (!p.first_date) return count;
  const first = formatDate(p.first_date, locale.value);
  if (!p.last_date || p.last_date === p.first_date) return `${count} · ${first}`;
  return `${count} · ${first} – ${formatDate(p.last_date, locale.value)}`;
}

const prefetched = new Set<string>();
function prefetchDetails(datepollId: string) {
  if (prefetched.has(datepollId)) return;
  prefetched.add(datepollId);
  void qc.prefetchQuery({
    queryKey: ["datepolls", "single", datepollId],
    queryFn: () => get(`/api/v1/datepolls/${datepollId}`),
  });
  void qc.prefetchQuery({
    queryKey: ["datepolls", datepollId, "summary"],
    queryFn: () => get(`/api/v1/datepolls/${datepollId}/summary`),
  });
}

function askArchive(p: DatepollListOut) {
  confirms.ask({
    header: t("datepolls.list.archiveConfirmTitle"),
    message: t("datepolls.list.archiveConfirmBody", { name: lt(p.name_nl, p.name_en) ?? "" }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("datepolls.list.archive"),
    accept: async () => {
      try {
        await archiveMutation.mutateAsync(p.id);
        toasts.success(t("datepolls.list.archived"));
      } catch {
        toasts.error(t("datepolls.list.archiveFail"));
      }
    },
  });
}
</script>

<template>
  <template v-if="auth.needsChapters">
    <AppHeader />
    <div class="container-wide stack">
      <h1>{{ t("datepolls.list.title") }}</h1>
      <p class="muted">{{ t("datepolls.list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.noChaptersTitle") }}</h2>
        <p class="muted">{{ t("dashboard.noChaptersBody") }}</p>
      </AppCard>
    </div>
  </template>

  <ListPageView
    v-else
    :title="t('datepolls.list.title')"
    :intro="t('datepolls.list.intro')"
    :items="sortedPolls"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('datepolls.list.searchPlaceholder')"
    :search-keys="(p: DatepollListOut) => [lt(p.name_nl, p.name_en) ?? '']"
    :empty-copy="t('datepolls.list.empty')"
    :no-matches-copy="t('datepolls.list.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #actions-leading>
      <router-link
        :to="{
          path: '/datepolls/new',
          query: chapterFilter ? { chapter: chapterFilter } : undefined,
        }"
      >
        <Button :label="t('datepolls.list.newDatepoll')" icon="pi pi-plus" />
      </router-link>
    </template>

    <template #row="{ item: p }">
      <EntityCard
        :public-url="publicDatepollUrl(p.slug)"
        :qr-src="datepollQrUrl(p.slug)"
        :copy-link-label="t('datepolls.share.copyLink')"
        :qr-label="t('datepolls.share.copyQr')"
        @mouseenter="prefetchDetails(p.id)"
        @focusin="prefetchDetails(p.id)"
        @copy-link="copyLink(p.slug)"
        @copy-qr="copyQr(p.slug)"
      >
        <template #title>
          <h3>
            {{ lt(p.name_nl, p.name_en) }}
            <span v-if="p.chapter_name" class="chapter-chip">{{ p.chapter_name }}</span>
          </h3>
        </template>

        <template #meta>
          <p class="muted">{{ dateRange(p) }}</p>
        </template>


        <template #actions>
          <router-link :to="`/datepolls/${p.id}/details`">
            <Button :label="t('datepolls.list.details')" icon="pi pi-info-circle" size="small" severity="secondary" />
          </router-link>
          <Button
            :label="t('datepolls.list.archive')"
            icon="pi pi-archive"
            size="small"
            severity="secondary"
            text
            @click="askArchive(p)"
          />
        </template>

        <template #count>{{ t("datepolls.list.responseCount", { n: p.submission_count }) }}</template>
      </EntityCard>
    </template>
  </ListPageView>
</template>
