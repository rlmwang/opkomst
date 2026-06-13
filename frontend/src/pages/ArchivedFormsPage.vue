<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import { useArchivedList } from "@/composables/useArchivedList";
import {
  type FormListOut,
  useArchivedForms,
  useDeleteForm,
  useRestoreForm,
} from "@/composables/useForms";

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
  query: (chapterId) => useArchivedForms({ chapterId }),
  restore: useRestoreForm(),
  remove: useDeleteForm(),
  prefix: "forms.archived",
});
</script>

<template>
  <ListPageView
    :title="t('forms.archived.title')"
    :intro="t('forms.archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('forms.archived.searchPlaceholder')"
    :search-keys="(f: FormListOut) => [f.name]"
    :empty-copy="t('forms.archived.empty')"
    :no-matches-copy="t('forms.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: f }">
      <AppCard :stack="false" class="row">
        <div>
          <h3>
            {{ f.name }}
            <span v-if="f.chapter_name" class="event-chapter-chip">{{ f.chapter_name }}</span>
          </h3>
        </div>
        <div class="row-actions">
          <Button :label="t('forms.archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restoreItem(f)" />
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('forms.archived.delete')"
            :aria-label="t('forms.archived.delete')"
            @click="askDelete(f)"
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
