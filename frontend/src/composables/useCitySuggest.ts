import { ref } from "vue";

import { makeAbortBox, parseCentroide, pdokLookup, pdokSuggest } from "@/lib/pdok";

export interface CitySuggestion {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
}

const RESULT_LIMIT = 8;

export function useCitySuggest() {
  // Each suggestion lacks coords (PDOK ``suggest`` only returns
  // ``id`` + ``weergavenaam``); coords come from a per-pick
  // ``/lookup`` round-trip in ``resolve()``.
  const results = ref<{ id: string; name: string }[]>([]);
  const abort = makeAbortBox();

  async function search(query: string): Promise<void> {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      results.value = [];
      return;
    }
    try {
      const docs = await pdokSuggest(trimmed, {
        fq: "type:woonplaats",
        rows: RESULT_LIMIT,
        signal: abort.next(),
      });
      // PDOK's ``weergavenaam`` for ``type:woonplaats`` is
      // ``"{city}, {municipality}, {province}"``. For most Dutch
      // cities the three are identical (Utrecht / Utrecht /
      // Utrecht), which is silly noise in a dropdown. Take the
      // first segment — it's the city name.
      results.value = docs.map((d) => ({
        id: d.id,
        name: d.weergavenaam.split(",")[0].trim(),
      }));
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        results.value = [];
      }
    }
  }

  async function resolve(id: string, name: string): Promise<CitySuggestion | null> {
    const doc = await pdokLookup(id, "id,weergavenaam,centroide_ll");
    if (!doc) return null;
    const point = parseCentroide(doc.centroide_ll);
    if (!point) return null;
    return { id, name, latitude: point.lat, longitude: point.lon };
  }

  return { results, search, resolve };
}
