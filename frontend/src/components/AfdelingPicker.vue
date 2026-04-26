<script setup lang="ts">
import AutoComplete, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "primevue/autocomplete";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { type Afdeling, useAfdelingenStore } from "@/stores/afdelingen";

const props = defineProps<{
  modelValue: Afdeling | null;
  /** When true, archived afdelingen show up as "restore?" suggestions. */
  showArchived?: boolean;
  placeholder?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: Afdeling | null];
}>();

const { t } = useI18n();
const store = useAfdelingenStore();

const suggestions = ref<Afdeling[]>([]);
const local = ref<Afdeling | string | null>(props.modelValue);

async function onComplete(e: AutoCompleteCompleteEvent) {
  suggestions.value = await store.search(e.query, props.showArchived ?? false);
}

function onSelect(e: AutoCompleteOptionSelectEvent) {
  const picked = e.value as Afdeling;
  local.value = picked;
  emit("update:modelValue", picked);
}

function clear() {
  local.value = null;
  emit("update:modelValue", null);
}

defineExpose({ clear });
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
