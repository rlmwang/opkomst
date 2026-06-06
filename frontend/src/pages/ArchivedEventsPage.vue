<script setup lang="ts">
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import {
  type EventOut,
  useArchivedEvents,
  useDeleteEvent,
  useRestoreEvent,
} from "@/composables/useEvents";
import { useGuardedMutation } from "@/composables/useGuardedMutation";
import { formatDateTime } from "@/lib/format";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t, locale } = useI18n();
const toasts = useToasts();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

// Chapter filter state — same shape as the dashboard so the URL
// param survives navigation between active and archived lists.
const chapterFilter = computed<string | null>(() => {
  const v = route.query.chapter;
  return typeof v === "string" && v ? v : null;
});

function setChapterFilter(value: string | null) {
  void router.replace({
    query: { ...route.query, chapter: value ?? undefined },
  });
}

const chapterOptions = computed(() => auth.user?.chapters ?? []);

const archivedQuery = useArchivedEvents({ chapterId: chapterFilter });
const archived = computed<EventOut[]>(() => archivedQuery.data.value ?? []);
const restoreMutation = useRestoreEvent();
const deleteMutation = useDeleteEvent();

// Hard-delete is irreversible. Setup-time wiring (per
// useGuardedMutation contract); the click handler just calls the
// returned function with the event row so the confirm copy can
// quote the event name.
const askDelete = useGuardedMutation(deleteMutation, (e: EventOut) => ({
  vars: e.id,
  ok: t("archived.deleteOk", { name: e.name }),
  fail: t("archived.deleteFail"),
  confirm: {
    header: t("archived.deleteConfirmTitle"),
    message: t("archived.deleteConfirmBody", { name: e.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("archived.delete"),
  },
}));

watch(archivedQuery.isError, (isError) => {
  if (isError) toasts.error(t("archived.loadFailed"));
});

const loaded = computed(() => !archivedQuery.isPending.value);

async function restore(e: EventOut) {
  try {
    await restoreMutation.mutateAsync(e.id);
    toasts.success(t("archived.restored", { name: e.name }));
  } catch {
    toasts.error(t("archived.restoreFail"));
  }
}
</script>

<template>
  <ListPageView
    :title="t('archived.title')"
    :intro="t('archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('archived.searchPlaceholder')"
    :search-keys="(e: EventOut) => [e.name, e.location]"
    :empty-copy="t('archived.empty')"
    :no-matches-copy="t('archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: e }">
      <AppCard :stack="false" class="row">
        <div>
          <h3>
            {{ e.name }}
            <span v-if="e.chapter_name" class="event-chapter-chip">{{ e.chapter_name }}</span>
          </h3>
          <p class="muted">
            {{ e.location }} · {{ formatDateTime(e.starts_at, locale) }}
          </p>
        </div>
        <div class="row-actions">
          <Button :label="t('archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restore(e)" />
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('archived.delete')"
            :aria-label="t('archived.delete')"
            @click="askDelete(e)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.row h3 { margin: 0 0 0.25rem; }
.row-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
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
</style>
