<script setup lang="ts">
import Button from "primevue/button";
import Select from "primevue/select";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";
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

const query = ref("");
const loaded = computed(() => !archivedQuery.isPending.value);

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return archived.value;
  return archived.value.filter(
    (e) => e.name.toLowerCase().includes(q) || e.location.toLowerCase().includes(q),
  );
});

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
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("archived.title") }}</h1>
    <p class="muted">{{ t("archived.intro") }}</p>

    <div class="actions-row">
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
        :placeholder="t('archived.searchPlaceholder')"
        class="search"
      />
    </div>

    <AppSkeleton v-if="!loaded" :rows="2" cards />

    <AppCard v-else-if="archived.length === 0" :stack="false">
      <p class="muted">{{ t("archived.empty") }}</p>
    </AppCard>

    <p v-else-if="filtered.length === 0" class="muted">{{ t("archived.noMatches") }}</p>

    <AppCard v-for="e in filtered" :key="e.id" :stack="false" class="row">
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
  </div>
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
.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}
.actions-row .search {
  flex: 1;
  min-width: 0;
  max-width: 24rem;
  margin-left: auto;
}
.chapter-filter {
  min-width: 12rem;
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
