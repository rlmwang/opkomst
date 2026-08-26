<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import { useArchivedList } from "@/composables/useArchivedList";
import { type FormListOut, useFormsApi } from "@/composables/useForms";

const { t, te } = useI18n();
const lt = useLocalizedText();
// One page, two products; the route says which (``useForms``).
const api = useFormsApi();
/** ``quizzes.<key>`` when there is one, ``forms.<key>`` otherwise: the
 *  two products share every string that is not about scoring. */
const L = (key: string, params?: Record<string, unknown>) => {
  const full = api.resource === "quizzes" && te(`quizzes.${key}`) ? `quizzes.${key}` : `forms.${key}`;
  return params ? t(full, params) : t(full);
};

const {
  chapterFilter,
  setChapterFilter,
  chapterOptions,
  archived,
  loaded,
  restoreItem,
  askDelete,
} = useArchivedList({
  query: (chapterId) => api.useArchived({ chapterId }),
  restore: api.useRestore(),
  remove: api.useDelete(),
  prefix: `${api.resource === "quizzes" ? "quizzes" : "forms"}.archived`,
});
</script>

<template>
  <ListPageView
    :title="L('archived.title')"
    :intro="L('archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="L('archived.searchPlaceholder')"
    :search-keys="(f: FormListOut) => [lt(f.name_nl, f.name_en) ?? '']"
    :empty-copy="L('archived.empty')"
    :no-matches-copy="L('archived.noMatches')"
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
          <Button :label="L('archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restoreItem(f)" />
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="L('archived.delete')"
            :aria-label="L('archived.delete')"
            @click="askDelete(f)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>
