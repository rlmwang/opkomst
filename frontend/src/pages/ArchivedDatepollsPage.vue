<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
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
  query: (chapterId) => useArchivedDatepolls({ chapterId }),
  restore: useRestoreDatepoll(),
  remove: useDeleteDatepoll(),
  prefix: "datepoll.archived",
});
</script>

<template>
  <ListPageView
    :title="t('datepoll.archived.title')"
    :intro="t('datepoll.archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('datepoll.archived.searchPlaceholder')"
    :search-keys="(p: DatepollListOut) => [lt(p.name_nl, p.name_en) ?? '']"
    :empty-copy="t('datepoll.archived.empty')"
    :no-matches-copy="t('datepoll.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: p }">
      <AppCard :stack="false" class="archive-row">
        <div>
          <h3>
            {{ lt(p.name_nl, p.name_en) }}
            <span v-if="p.chapter_name" class="chapter-chip">{{ p.chapter_name }}</span>
          </h3>
        </div>
        <div class="archive-row-actions">
          <AppButton :label="t('datepoll.archived.restore')" icon="replay" size="small" severity="secondary" @click="restoreItem(p)" />
          <AppButton
            icon="trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('datepoll.archived.delete')"
            :aria-label="t('datepoll.archived.delete')"
            @click="askDelete(p)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>
