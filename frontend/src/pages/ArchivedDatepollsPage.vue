<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import { useArchivedList } from "@/composables/useArchivedList";
import {
  type DatepollListOut,
  useArchivedDatepolls,
  useDeleteDatepoll,
  useRestoreDatepoll,
} from "@/composables/useDatepolls";

const { t } = useI18n();

const {
  chapterFilter,
  setChapterFilter,
  chapterOptions,
  archived,
  loaded,
  restoreItem,
  askDelete,
} = useArchivedList({
  query: (chapterId) => useArchivedDatepolls({ chapterId }),
  restore: useRestoreDatepoll(),
  remove: useDeleteDatepoll(),
  prefix: "datepolls.archived",
});
</script>

<template>
  <ListPageView
    :title="t('datepolls.archived.title')"
    :intro="t('datepolls.archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('datepolls.archived.searchPlaceholder')"
    :search-keys="(p: DatepollListOut) => [p.name]"
    :empty-copy="t('datepolls.archived.empty')"
    :no-matches-copy="t('datepolls.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: p }">
      <AppCard :stack="false" class="row">
        <div>
          <h3>
            {{ p.name }}
            <span v-if="p.chapter_name" class="event-chapter-chip">{{ p.chapter_name }}</span>
          </h3>
        </div>
        <div class="row-actions">
          <Button :label="t('datepolls.archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restoreItem(p)" />
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('datepolls.archived.delete')"
            :aria-label="t('datepolls.archived.delete')"
            @click="askDelete(p)"
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
.row h3 { margin: 0; }
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
