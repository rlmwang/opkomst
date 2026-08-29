<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
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
const lt = useLocalizedText();

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
  prefix: "chore.archived",
});
</script>

<template>
  <ListPageView
    :title="t('chore.archived.title')"
    :intro="t('chore.archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('chore.archived.searchPlaceholder')"
    :search-keys="(r: RosterListOut) => [lt(r.name_nl, r.name_en) ?? '']"
    :empty-copy="t('chore.archived.empty')"
    :no-matches-copy="t('chore.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: r }">
      <AppCard :stack="false" class="archive-row">
        <div>
          <h3>
            {{ lt(r.name_nl, r.name_en) }}
            <span v-if="r.chapter_name" class="chapter-chip">{{ r.chapter_name }}</span>
          </h3>
        </div>
        <div class="archive-row-actions">
          <AppButton :label="t('chore.archived.restore')" icon="replay" size="small" severity="secondary" @click="restoreItem(r)" />
          <AppButton
            icon="trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('chore.archived.delete')"
            :aria-label="t('chore.archived.delete')"
            @click="askDelete(r)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>
