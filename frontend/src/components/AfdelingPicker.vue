<script setup lang="ts">
import AutoComplete, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "primevue/autocomplete";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { type Afdeling, useAfdelingenStore } from "@/stores/afdelingen";

const props = defineProps<{
  /** When true, archived afdelingen surface in suggestions tagged
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
  /** User picked an existing afdeling (active or archived). The
   * caller decides what to do — for active picks usually a no-op,
   * for archived a restore. */
  pick: [value: Afdeling];
  /** User typed text that doesn't match an existing afdeling and
   * pressed Enter — caller should create a new one with this name. */
  create: [name: string];
}>();

const { t } = useI18n();
const store = useAfdelingenStore();

const suggestions = ref<Afdeling[]>([]);
// AutoComplete sets the bound value to the option object on select
// and to the typed string until then. We exploit that distinction:
// string at Enter-time means "no match was picked, treat as create".
const local = ref<Afdeling | string | null>(null);

async function onComplete(e: AutoCompleteCompleteEvent) {
  const all = await store.search(e.query, true);
  suggestions.value = props.archivedOnly ? all.filter((a) => a.archived) : all;
}

function onSelect(e: AutoCompleteOptionSelectEvent) {
  emit("pick", e.value as Afdeling);
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
    :placeholder="placeholder ?? t('afdelingen.pickerPlaceholder')"
    :delay="200"
    fluid
    @complete="onComplete"
    @option-select="onSelect"
    @keyup.enter="onEnter"
  >
    <template #option="{ option }">
      <div class="option" :class="{ archived: (option as Afdeling).archived }">
        <span>{{ (option as Afdeling).name }}</span>
        <span v-if="(option as Afdeling).archived" class="tag">{{ t("afdelingen.archivedTag") }}</span>
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
