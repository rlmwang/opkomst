<script setup lang="ts">
import AutoComplete, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "primevue/autocomplete";
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { type LocationPick, type NominatimResult, useNominatim } from "@/composables/useNominatim";

const { t } = useI18n();

const props = defineProps<{
  modelValue: string;
  latitude: number | null;
  longitude: number | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  "update:coords": [coords: { latitude: number | null; longitude: number | null }];
}>();

const { results, search, pick } = useNominatim();
const local = ref<string>(props.modelValue);

watch(
  () => props.modelValue,
  (v) => {
    if (v !== local.value) local.value = v;
  },
);

function onComplete(e: AutoCompleteCompleteEvent) {
  void search(e.query);
}

function onSelect(e: AutoCompleteOptionSelectEvent) {
  const picked: LocationPick = pick(e.value as NominatimResult);
  local.value = picked.display_name;
  emit("update:modelValue", picked.display_name);
  emit("update:coords", { latitude: picked.latitude, longitude: picked.longitude });
}

function onBlur() {
  // Free-typed text without a Nominatim pick → keep the string, drop coords.
  // The user can still save the event; the public page will just skip the map.
  emit("update:modelValue", local.value);
  if (props.latitude !== null || props.longitude !== null) {
    // The string no longer matches the picked suggestion; assume the user
    // edited the text and the old coords are stale.
    if (results.value.every((r) => r.display_name !== local.value)) {
      emit("update:coords", { latitude: null, longitude: null });
    }
  }
}
</script>

<template>
  <AutoComplete
    v-model="local"
    :suggestions="results"
    option-label="display_name"
    :placeholder="t('event.location')"
    :delay="300"
    :min-length="3"
    fluid
    @complete="onComplete"
    @option-select="onSelect"
    @blur="onBlur"
  >
    <template #option="{ option }">
      <div class="suggestion">{{ (option as NominatimResult).display_name }}</div>
    </template>
  </AutoComplete>
</template>

<style scoped>
.suggestion {
  font-size: 0.875rem;
  white-space: normal;
  line-height: 1.3;
}
</style>
