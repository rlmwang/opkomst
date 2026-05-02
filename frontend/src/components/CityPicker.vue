<script setup lang="ts">
import AutoComplete, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "primevue/autocomplete";
import { ref, watch } from "vue";
import { type CitySuggestion, useCitySuggest } from "@/composables/useCitySuggest";

interface CityValue {
  city: string | null;
  city_lat: number | null;
  city_lon: number | null;
}

const props = defineProps<{
  modelValue: CityValue;
  placeholder: string;
}>();

const emit = defineEmits<{ "update:modelValue": [value: CityValue] }>();

const { results, search, resolve } = useCitySuggest();

// Defensively normalise the inbound city — historical rows may have
// been saved as PDOK's verbose ``"{city}, {municipality}, {province}"``
// (e.g., "Utrecht, Utrecht, Utrecht"). Display only the first
// segment so the input never shows the redundant noise.
function normalizeCity(v: string | null | undefined): string {
  if (!v) return "";
  return v.split(",")[0].trim();
}

const local = ref<string>(normalizeCity(props.modelValue.city));

watch(
  () => props.modelValue.city,
  (v) => {
    const next = normalizeCity(v);
    if (next !== local.value) local.value = next;
  },
);

function onComplete(e: AutoCompleteCompleteEvent) {
  void search(e.query);
}

async function onSelect(e: AutoCompleteOptionSelectEvent) {
  const choice = e.value as { id: string; name: string };
  local.value = choice.name;
  const resolved: CitySuggestion | null = await resolve(choice.id, choice.name);
  if (!resolved) return;
  emit("update:modelValue", {
    city: resolved.name,
    city_lat: resolved.latitude,
    city_lon: resolved.longitude,
  });
}

function onBlur() {
  // If the user typed text that doesn't match a picked suggestion,
  // clear the city tuple — a name without coords is useless for
  // address-bias and we'd rather store NULL than something
  // misleading.
  if (local.value.trim() === "") {
    emit("update:modelValue", { city: null, city_lat: null, city_lon: null });
    return;
  }
  if (local.value !== props.modelValue.city) {
    // Free-typed text, never picked — drop coords.
    emit("update:modelValue", { city: null, city_lat: null, city_lon: null });
  }
}
</script>

<template>
  <AutoComplete
    v-model="local"
    :suggestions="results"
    option-label="name"
    :placeholder="placeholder"
    :delay="300"
    :min-length="2"
    fluid
    @complete="onComplete"
    @option-select="onSelect"
    @blur="onBlur"
  />
</template>
