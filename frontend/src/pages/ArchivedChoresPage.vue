<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import { useArchivedList } from "@/composables/useArchivedList";
import {
  type RosterListOut,
  useArchivedRosters,
  useDeleteRoster,
  useRestoreRoster,
} from "@/composables/useChores";

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
  query: (chapterId) => useArchivedRosters({ chapterId }),
  restore: useRestoreRoster(),
  remove: useDeleteRoster(),
  prefix: "chores.archived",
});
</script>

<template>
  <ListPageView
    :title="t('chores.archived.title')"
    :intro="t('chores.archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('chores.archived.searchPlaceholder')"
    :search-keys="(r: RosterListOut) => [r.name]"
    :empty-copy="t('chores.archived.empty')"
    :no-matches-copy="t('chores.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: r }">
      <AppCard :stack="false" class="row">
        <div>
          <h3>
            {{ r.name }}
            <span v-if="r.chapter_name" class="chapter-chip">{{ r.chapter_name }}</span>
          </h3>
        </div>
        <div class="row-actions">
          <Button :label="t('chores.archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restoreItem(r)" />
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('chores.archived.delete')"
            :aria-label="t('chores.archived.delete')"
            @click="askDelete(r)"
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
</style>
