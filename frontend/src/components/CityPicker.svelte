<script lang="ts">
import AutoCompleteField, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "@/components/AutoCompleteField.svelte";
import { type CitySuggestion, useCitySuggest } from "@/composables/useCitySuggest.svelte";

interface CityValue {
  city: string | null;
  city_lat: number | null;
  city_lon: number | null;
}

let {
  value = $bindable(),
  placeholder,
}: { value: CityValue; placeholder: string } = $props();

const suggest = useCitySuggest();

// Defensively normalise the inbound city: historical rows may have been
// saved as PDOK's verbose ``"{city}, {municipality}, {province}"``
// ("Utrecht, Utrecht, Utrecht"). Display only the first segment so the
// input never shows the redundant noise.
function normalizeCity(v: string | null | undefined): string {
  if (!v) return "";
  return v.split(",")[0].trim();
}

let local = $state<string>(normalizeCity(value.city));

// The value arriving from the server, or a revert, resets the box.
let lastSeen = value.city;
$effect(() => {
  if (value.city === lastSeen) return;
  lastSeen = value.city;
  const next = normalizeCity(value.city);
  if (next !== local) local = next;
});

function onComplete(e: AutoCompleteCompleteEvent) {
  void suggest.search(e.query);
}

async function onSelect(e: AutoCompleteOptionSelectEvent) {
  const choice = e.value as { id: string; name: string };
  local = choice.name;
  const resolved: CitySuggestion | null = await suggest.resolve(choice.id, choice.name);
  if (!resolved) return;
  value = { city: resolved.name, city_lat: resolved.latitude, city_lon: resolved.longitude };
}

function onBlur() {
  // If the user typed text that doesn't match a picked suggestion, clear
  // the city tuple: a name without coordinates is useless for
  // address-bias and NULL is better than something misleading.
  if (local.trim() === "" || local !== value.city) {
    value = { city: null, city_lat: null, city_lon: null };
  }
}
</script>

<AutoCompleteField
  bind:value={local}
  suggestions={suggest.results}
  optionLabel="name"
  {placeholder}
  delay={300}
  minLength={2}
  fluid
  oncomplete={onComplete}
  onoptionSelect={onSelect}
  onblur={onBlur}
/>
