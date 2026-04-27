<script setup lang="ts">
import AutoComplete, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "primevue/autocomplete";
import InputText from "primevue/inputtext";
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { type LocationPick, type NominatimResult, useNominatim } from "@/composables/useNominatim";

const { t } = useI18n();

const props = defineProps<{
  modelValue: string;
  latitude: number | null;
  longitude: number | null;
  /** Optional proximity hint: when set, address suggestions are
   * re-ranked by distance from this point (used to bias toward the
   * organiser's chapter's home city). */
  biasLat?: number | null;
  biasLon?: number | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  "update:coords": [coords: { latitude: number | null; longitude: number | null }];
}>();

const { results, search, pick, lookup } = useNominatim();

// AutoComplete value — the picked anchor (street, city, country) or
// free-typed text. The composed value with house number lives in
// ``modelValue`` (emitted up).
const local = ref<string>(props.modelValue);

// Last successful pick — kept so the house-number field can recompose
// "{street} {nr}, {city}, {country}" without re-running geocoding.
// Cleared when the user free-types after a pick.
const picked = ref<LocationPick | null>(null);
const houseNumber = ref<string>("");

watch(
  () => props.modelValue,
  (v) => {
    if (v !== composedValue()) local.value = v;
  },
);

function composedValue(): string {
  if (!picked.value) return local.value;
  const street = picked.value.street;
  const nr = houseNumber.value.trim();
  const streetWithNr = street ? (nr ? `${street} ${nr}` : street) : null;
  return [streetWithNr, picked.value.city, picked.value.country].filter(Boolean).join(", ");
}

function emitValue() {
  emit("update:modelValue", composedValue());
}

function onComplete(e: AutoCompleteCompleteEvent) {
  const bias =
    props.biasLat != null && props.biasLon != null
      ? { lat: props.biasLat, lon: props.biasLon }
      : undefined;
  void search(e.query, bias);
}

async function onSelect(e: AutoCompleteOptionSelectEvent) {
  // PDOK ``suggest`` doesn't include coords; pick() does the
  // lookup-by-id round-trip. Show the picked text immediately so
  // there's no UI freeze, then update coords when the lookup lands.
  const r = e.value as NominatimResult;
  local.value = r.display_name;
  houseNumber.value = "";
  picked.value = {
    display_name: r.display_name,
    latitude: 0,
    longitude: 0,
    street: r.street,
    city: r.city,
    country: r.country,
  };
  emit("update:modelValue", composedValue());
  const resolved = await pick(r);
  if (!resolved) return;
  picked.value = resolved;
  emit("update:coords", { latitude: resolved.latitude, longitude: resolved.longitude });
}

function onBlur() {
  // Free-typed text without a pick → keep the string, drop coords.
  // The user can still save the event; the public page will just skip the map.
  if (picked.value && local.value !== picked.value.display_name) {
    // The anchor was edited away from what we picked — treat as
    // free-text again, hide the number field.
    picked.value = null;
    houseNumber.value = "";
  }
  if (props.latitude !== null || props.longitude !== null) {
    if (results.value.every((r) => r.display_name !== local.value) && !picked.value) {
      emit("update:coords", { latitude: null, longitude: null });
    }
  }
  emitValue();
}

function onHouseNumberInput() {
  emitValue();
}

async function onHouseNumberBlur() {
  emitValue();
  // Refine coords against the full address. PDOK's ``type:adres``
  // index is per-housenumber from BAG, so any non-null result is
  // already a real building — no need to second-guess the street
  // match (the previous string-equality guard was rejecting valid
  // refinements over case / encoding differences). When nothing
  // matches we silently keep the street-midpoint coords from the
  // original pick.
  if (!picked.value) return;
  const nr = houseNumber.value.trim();
  if (!nr) return;
  const street = picked.value.street;
  if (!street) return;
  const refined = await lookup(`${street} ${nr} ${picked.value.city ?? ""}`.trim());
  if (refined) {
    emit("update:coords", { latitude: refined.latitude, longitude: refined.longitude });
  }
}
</script>

<template>
  <div class="picker">
    <AutoComplete
      v-model="local"
      :suggestions="results"
      option-label="display_name"
      :placeholder="t('event.location')"
      :delay="300"
      :min-length="3"
      fluid
      class="street"
      @complete="onComplete"
      @option-select="onSelect"
      @blur="onBlur"
    >
      <template #option="{ option }">
        <div class="suggestion">{{ (option as NominatimResult).display_name }}</div>
      </template>
    </AutoComplete>
    <InputText
      v-if="picked"
      v-model="houseNumber"
      :placeholder="t('event.houseNumber')"
      class="nr"
      @input="onHouseNumberInput"
      @blur="onHouseNumberBlur"
    />
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  gap: 0.5rem;
  align-items: stretch;
}
.street {
  flex: 1;
  min-width: 0;
}
.nr {
  width: 6rem;
  flex-shrink: 0;
}
.suggestion {
  font-size: 0.875rem;
  white-space: normal;
  line-height: 1.3;
}
</style>
