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

const noChapters = computed(
  () => auth.isApproved && (auth.user?.chapters?.length ?? 0) === 0,
);

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
    message: t("datepolls.list.archiveConfirmBody", { name: p.name }),
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
  <template v-if="!auth.isApproved">
    <AppHeader />
    <div class="container stack">
      <h1>{{ t("datepolls.list.title") }}</h1>
      <p class="muted">{{ t("datepolls.list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.pendingTitle") }}</h2>
        <p>{{ t("dashboard.pendingBody") }}</p>
      </AppCard>
    </div>
  </template>

  <template v-else-if="noChapters">
    <AppHeader />
    <div class="container stack">
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
    :search-keys="(p: DatepollListOut) => [p.name]"
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
      <AppCard
        :stack="false"
        class="poll-card"
        @mouseenter="prefetchDetails(p.id)"
        @focusin="prefetchDetails(p.id)"
      >
        <div class="poll-main">
          <div class="poll-summary">
            <h3>
              {{ p.name }}
              <span v-if="p.chapter_name" class="chapter-chip">{{ p.chapter_name }}</span>
            </h3>
            <p class="muted dates-line">{{ dateRange(p) }}</p>
            <div class="link-row">
              <a :href="publicDatepollUrl(p.slug)" target="_blank" rel="noopener">{{ publicDatepollUrl(p.slug) }}</a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                v-tooltip.top="t('datepolls.share.copyLink')"
                :aria-label="t('datepolls.share.copyLink')"
                @click="copyLink(p.slug)"
              />
            </div>
          </div>

          <div class="actions">
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
          </div>
        </div>

        <div class="poll-side">
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('datepolls.share.copyQr')"
            :aria-label="t('datepolls.share.copyQr')"
            @click="copyQr(p.slug)"
          >
            <img :src="datepollQrUrl(p.slug)" alt="" class="qr" />
          </button>
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>

<style scoped>
.poll-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.25rem;
  align-items: stretch;
}
.poll-main {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  min-width: 0;
}
.poll-summary h3 { margin: 0 0 0.25rem; }
.dates-line { margin: 0 0 0.25rem; font-size: 0.875rem; }
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
  margin-top: auto;
}
.poll-side {
  display: flex;
  align-items: center;
  justify-content: flex-end;
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
  .poll-card {
    grid-template-columns: 1fr;
  }
  .poll-side {
    justify-content: flex-end;
  }
}
</style>
