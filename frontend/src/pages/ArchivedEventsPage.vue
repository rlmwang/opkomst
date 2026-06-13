<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import { useArchivedList } from "@/composables/useArchivedList";
import {
  type EventOut,
  useArchivedEvents,
  useDeleteEvent,
  useRestoreEvent,
} from "@/composables/useEvents";
import { formatDateTime } from "@/lib/format";

const { t, locale } = useI18n();

const {
  chapterFilter,
  setChapterFilter,
  chapterOptions,
  archived,
  loaded,
  restoreItem,
  askDelete,
} = useArchivedList({
  query: (chapterId) => useArchivedEvents({ chapterId }),
  restore: useRestoreEvent(),
  remove: useDeleteEvent(),
  prefix: "archived",
});
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
          <Button :label="t('archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restoreItem(e)" />
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
