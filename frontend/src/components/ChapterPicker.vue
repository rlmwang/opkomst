<script setup lang="ts">
import AutoComplete, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "primevue/autocomplete";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import type { Chapter } from "@/api/types";
import { get } from "@/api/client";

export type { Chapter };

const props = defineProps<{
  /** When true, archived chapters surface in suggestions tagged
   * "restore?" so the caller can decide what to do with a pick. */
  showArchived?: boolean;
  /** When true, the picker ONLY surfaces archived suggestions —
   * active chapters are filtered out. The add-bar on the admin page
   * uses this so typing an existing active name doesn't pop a "no-op"
   * suggestion; it falls through to create (the backend's dupe check
   * rejects with 409). */
  archivedOnly?: boolean;
  placeholder?: string;
}>();

const emit = defineEmits<{
  /** User picked an existing chapter (active or archived). The
   * caller decides what to do — for active picks usually a no-op,
   * for archived a restore. */
  pick: [value: Chapter];
  /** User typed text that doesn't match an existing chapter and
   * pressed Enter — caller should create a new one with this name. */
  create: [name: string];
}>();

const { t } = useI18n();

const suggestions = ref<Chapter[]>([]);
// AutoComplete sets the bound value to the option object on select
// and to the typed string until then. We exploit that distinction:
// string at Enter-time means "no match was picked, treat as create".
const local = ref<Chapter | string | null>(null);

async function onComplete(e: AutoCompleteCompleteEvent) {
  // Direct fetch: the picker is its own little island and shouldn't
  // share cache with the page-level chapter list (the picker always
  // wants archived results so the user can pick-to-restore; the
  // page list usually doesn't).
  const list = await get<Chapter[]>("/api/v1/chapters?include_archived=true");
  const q = e.query.trim().toLowerCase();
  const matched = q ? list.filter((a) => a.name.toLowerCase().includes(q)) : list;
  suggestions.value = props.archivedOnly ? matched.filter((a) => a.archived) : matched;
}

function onSelect(e: AutoCompleteOptionSelectEvent) {
  emit("pick", e.value as Chapter);
  local.value = null;
}

function onEnter() {
  if (typeof local.value === "string" && local.value.trim()) {
    emit("create", local.value.trim());
    local.value = null;
  }
}
</script>

<template>
  <AutoComplete
    v-model="local"
    :suggestions="suggestions"
    option-label="name"
    :placeholder="placeholder ?? t('chapters.pickerPlaceholder')"
    :delay="200"
    fluid
    @complete="onComplete"
    @option-select="onSelect"
    @keyup.enter="onEnter"
  >
    <template #option="{ option }">
      <div class="option" :class="{ archived: (option as Chapter).archived }">
        <span>{{ (option as Chapter).name }}</span>
        <span v-if="(option as Chapter).archived" class="tag">{{ t("chapters.archivedTag") }}</span>
      </div>
    </template>
  </AutoComplete>
</template>

<style scoped>
.option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 0.75rem;
}
.option.archived span:first-child {
  color: var(--brand-text-muted);
  font-style: italic;
}
.tag {
  font-size: 0.75rem;
  color: var(--brand-red);
  background: #fbdadc;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
}
</style>
