<script setup lang="ts" generic="T extends { id: string }">
import Select from "primevue/select";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";

/**
 * Shared shell for "managed resource" list pages — the active and
 * archive variants for Events today; Forms once that feature
 * lands. Owns the page header, the title + intro, the
 * actions-row (chapter filter + search + slotted leading
 * controls), the loading skeleton, and the empty-state / no-match
 * branches.
 *
 * Per-page concerns stay outside the shell: the data source (a
 * Vue Query composable), sort order (applied to ``items`` before
 * it arrives), pre-shell guard banners (e.g. the "no chapters
 * yet" onboarding card), mutation handlers, error toasts.
 *
 * Search is name+free-text — the parent supplies a
 * ``searchKeys`` function that returns the haystack strings for
 * a row. The filter is case-insensitive substring across the
 * returned strings.
 */

interface ChapterOption {
  id: string;
  name: string;
}

const props = defineProps<{
  title: string;
  intro?: string;
  items: T[];
  loaded: boolean;
  chapterFilter: string | null;
  chapterOptions: ChapterOption[];
  searchPlaceholder: string;
  /** Strings to search through for a given row. Multiple haystacks
   * mean any-substring match. */
  searchKeys: (item: T) => string[];
  emptyCopy: string;
  noMatchesCopy: string;
  skeletonRows?: number;
}>();

const emit = defineEmits<{
  "update:chapterFilter": [string | null];
}>();

const { t } = useI18n();

const query = ref("");

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return props.items;
  return props.items.filter((item) =>
    props.searchKeys(item).some((s) => s.toLowerCase().includes(q)),
  );
});
</script>

<template>
  <AppHeader />
  <div class="container-wide stack">
    <h1>{{ title }}</h1>
    <p v-if="intro" class="muted">{{ intro }}</p>

    <div class="actions-row">
      <!-- Optional leading control (e.g. "+ New event" on active,
           nothing on archive). The chapter Select + Search always
           render. -->
      <slot name="actions-leading" />
      <!-- No chapters to filter by, no filter. A personal account has
           none at all; an organisation's member always has one. -->
      <Select
        v-if="chapterOptions.length > 0"
        :model-value="chapterFilter"
        :options="[{ id: null, name: t('dashboard.chapterFilterAll') }, ...chapterOptions]"
        option-label="name"
        option-value="id"
        :placeholder="t('dashboard.chapterFilterAll')"
        class="chapter-filter"
        @update:model-value="(v) => emit('update:chapterFilter', v)"
      />
      <SearchInput
        v-model="query"
        :placeholder="searchPlaceholder"
        class="search"
      />
    </div>

    <AppSkeleton v-if="!loaded" :rows="skeletonRows ?? 3" cards />

    <AppCard v-else-if="items.length === 0" :stack="false">
      <p class="muted">{{ emptyCopy }}</p>
    </AppCard>

    <p v-else-if="filtered.length === 0" class="muted">{{ noMatchesCopy }}</p>

    <template v-else>
      <template v-for="item in filtered" :key="item.id">
        <slot name="row" :item="item" />
      </template>
    </template>
  </div>
</template>

<style scoped>
.actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
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

/* Below the container width there isn't room to sit the 12rem
 * chapter filter beside the search box: the filter kept its
 * fixed width and the search collapsed to whatever was left,
 * which on a phone was roughly a third of the row. Rather than
 * split the row into two cramped halves, every control takes the
 * full width and stacks — the search field is the one that
 * actually needs the space, and full-width rows give all three
 * a comfortable tap target. */
@media (max-width: 720px) {
  .actions-row > * {
    flex: 1 1 100%;
    min-width: 0;
  }
  .actions-row .search {
    max-width: none;
    margin-left: 0;
  }
  /* The slotted "+ New …" link wraps its button, so the width
   * has to be pushed through to the button itself. */
  .actions-row :deep(.p-button) {
    width: 100%;
    justify-content: center;
  }
}
</style>
