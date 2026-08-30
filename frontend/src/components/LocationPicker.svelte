<script lang="ts">
import AutoCompleteField, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "@/components/AutoCompleteField.svelte";
import AppInput from "@/components/AppInput.svelte";
import { t } from "@/i18n.svelte";
import { type LocationPick, type NominatimResult, useNominatim } from "@/composables/useNominatim.svelte";

let {
  value = $bindable(),
  latitude,
  longitude,
  biasLat,
  biasLon,
  oncoords,
}: {
  value: string;
  latitude: number | null;
  longitude: number | null;
  /** Optional proximity hint: when set, address suggestions are
   *  re-ranked by distance from this point, to bias toward the
   *  organiser's chapter's home city. */
  biasLat?: number | null;
  biasLon?: number | null;
  oncoords: (coords: { latitude: number | null; longitude: number | null }) => void;
} = $props();

const nominatim = useNominatim();

// The field's value: the picked anchor (street, city, country) or
// free-typed text. The composed value with the house number is what
// goes back up.
let local = $state<string>(value);

// Last successful pick, kept so the house-number field can recompose
// "{street} {nr}, {city}, {country}" without re-running geocoding.
// Cleared when the user free-types after a pick.
let picked = $state<LocationPick | null>(null);
let houseNumber = $state<string>("");

function composedValue(): string {
  if (!picked) return local;
  const street = picked.street;
  const nr = houseNumber.trim();
  const streetWithNr = street ? (nr ? `${street} ${nr}` : street) : null;
  return [streetWithNr, picked.city, picked.country].filter(Boolean).join(", ");
}

// A value arriving from the server, or a revert, resets the box; a
// value this component just composed does not.
let lastSeen = value;
$effect(() => {
  if (value === lastSeen) return;
  lastSeen = value;
  if (value !== composedValue()) local = value;
});

function emitValue() {
  value = composedValue();
  lastSeen = value;
}

function onComplete(e: AutoCompleteCompleteEvent) {
  const bias = biasLat != null && biasLon != null ? { lat: biasLat, lon: biasLon } : undefined;
  void nominatim.search(e.query, bias);
}

async function onSelect(e: AutoCompleteOptionSelectEvent) {
  // PDOK's ``suggest`` doesn't include coordinates; ``pick`` does the
  // lookup-by-id round trip. Show the picked text immediately so there
  // is no freeze, then update the coordinates when the lookup lands.
  const r = e.value as NominatimResult;
  local = r.display_name;
  houseNumber = "";
  picked = {
    display_name: r.display_name,
    latitude: 0,
    longitude: 0,
    street: r.street,
    city: r.city,
    country: r.country,
  };
  emitValue();
  const resolved = await nominatim.pick(r);
  if (!resolved) return;
  picked = resolved;
  oncoords({ latitude: resolved.latitude, longitude: resolved.longitude });
}

function onBlur() {
  // Free-typed text without a pick: keep the string, drop the
  // coordinates. The event still saves; the public page skips the map.
  if (picked && local !== picked.display_name) {
    // The anchor was edited away from what was picked, so it is
    // free text again and the number field goes.
    picked = null;
    houseNumber = "";
  }
  if (latitude !== null || longitude !== null) {
    if (nominatim.results.every((r) => r.display_name !== local) && !picked) {
      oncoords({ latitude: null, longitude: null });
    }
  }
  emitValue();
}

async function onHouseNumberBlur() {
  emitValue();
  // Refine the coordinates against the full address. PDOK's
  // ``type:adres`` index is per house number from BAG, so any non-null
  // result is already a real building: no need to second-guess the
  // street match, and the previous string-equality guard was rejecting
  // valid refinements over case and encoding differences. When nothing
  // matches, the street-midpoint coordinates from the original pick
  // silently stand.
  if (!picked) return;
  const nr = houseNumber.trim();
  if (!nr) return;
  const street = picked.street;
  if (!street) return;
  const refined = await nominatim.lookup(`${street} ${nr} ${picked.city ?? ""}`.trim());
  if (refined) oncoords({ latitude: refined.latitude, longitude: refined.longitude });
}
</script>

<div class="picker">
  <AutoCompleteField
    bind:value={local}
    suggestions={nominatim.results}
    optionLabel="display_name"
    placeholder={t("event.location")}
    delay={300}
    minLength={3}
    fluid
    class="street"
    oncomplete={onComplete}
    onoptionSelect={onSelect}
    onblur={onBlur}
  >
    {#snippet optionSnippet({ option })}
      <div class="suggestion">{(option as NominatimResult).display_name}</div>
    {/snippet}
  </AutoCompleteField>
  {#if picked}
    <AppInput
      bind:value={houseNumber}
      placeholder={t("event.houseNumber")}
      class="nr"
      onblur={onHouseNumberBlur}
    />
  {/if}
</div>

<style>
.picker {
  display: flex;
  gap: 0.5rem;
  align-items: stretch;
}
:global(.street) {
  flex: 1;
  min-width: 0;
}
:global(.nr) {
  width: 6rem;
  flex-shrink: 0;
}
:global(.suggestion) {
  font-size: 0.875rem;
  white-space: normal;
  line-height: 1.3;
}
</style>
