<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
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
import { recurrenceHint } from "@/lib/recurrence";

const { t, locale } = useI18n();
const lt = useLocalizedText();

function hint(e: EventOut): string {
  return recurrenceHint(t, e);
}

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
    :search-keys="(e: EventOut) => [lt(e.name_nl, e.name_en) ?? '', e.location ?? '']"
    :empty-copy="t('archived.empty')"
    :no-matches-copy="t('archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: e }">
      <AppCard :stack="false" class="archive-row">
        <div>
          <h3>
            {{ lt(e.name_nl, e.name_en) }}
            <span v-if="e.chapter_name" class="chapter-chip">{{ e.chapter_name }}</span>
          </h3>
          <p class="muted">
            <template v-if="e.location">{{ e.location }} · </template>
            {{ formatDateTime(e.next_starts_at ?? `${e.starts_on}T${e.start_time}`, locale) }} ·
            {{ hint(e) }}
          </p>
        </div>
        <div class="archive-row-actions">
          <AppButton :label="t('archived.restore')" icon="replay" size="small" severity="secondary" @click="restoreItem(e)" />
          <AppButton
            icon="trash"
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
