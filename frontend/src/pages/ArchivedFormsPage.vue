<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
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
    :search-keys="(f: FormListOut) => [lt(f.name_nl, f.name_en) ?? '']"
    :empty-copy="t('forms.archived.empty')"
    :no-matches-copy="t('forms.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: f }">
      <AppCard :stack="false" class="archive-row">
        <div>
          <h3>
            {{ lt(f.name_nl, f.name_en) }}
            <span v-if="f.chapter_name" class="chapter-chip">{{ f.chapter_name }}</span>
          </h3>
        </div>
        <div class="archive-row-actions">
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
