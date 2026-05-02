import { ref } from "vue";

import { type PdokDoc, makeAbortBox, parseCentroide, pdokFree, pdokLookup, pdokSuggest } from "@/lib/pdok";

export interface NominatimResult {
  id: string;
  display_name: string;
  lat: string;
  lon: string;
  place_id: number;
  street: string | null;
  city: string | null;
  country: string | null;
}

export interface LocationPick {
  display_name: string;
  latitude: number;
  longitude: number;
  street: string | null;
  city: string | null;
  country: string | null;
}

const RESULT_LIMIT = 10;
const FULL_FL = "id,weergavenaam,straatnaam,woonplaatsnaam,gemeentenaam,centroide_ll";

function _toPick(doc: PdokDoc): LocationPick | null {
  const point = parseCentroide(doc.centroide_ll);
  if (!point) return null;
  return {
    display_name: doc.weergavenaam,
    latitude: point.lat,
    longitude: point.lon,
    street: doc.straatnaam ?? null,
    city: doc.woonplaatsnaam ?? doc.gemeentenaam ?? null,
    country: "Nederland",
  };
}

export function useNominatim() {
  const results = ref<NominatimResult[]>([]);
  const searching = ref(false);
  const abort = makeAbortBox();

  async function search(query: string, bias?: { lat: number; lon: number }): Promise<void> {
    const trimmed = query.trim();
    if (trimmed.length < 3) {
      results.value = [];
      return;
    }

    searching.value = true;
    try {
      const docs = await pdokSuggest(trimmed, {
        fq: "type:weg",
        rows: RESULT_LIMIT,
        bias,
        signal: abort.next(),
      });
      results.value = docs.map((d, i) => ({
        id: d.id,
        place_id: i,
        display_name: d.weergavenaam,
        lat: "",
        lon: "",
        street: d.straatnaam ?? null,
        city: d.woonplaatsnaam ?? d.gemeentenaam ?? null,
        country: "Nederland",
      }));
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        results.value = [];
      }
    } finally {
      searching.value = false;
    }
  }

  /** Pick a suggestion: resolves coords from PDOK on demand. */
  async function pick(r: NominatimResult): Promise<LocationPick | null> {
    const doc = await pdokLookup(r.id, FULL_FL);
    if (!doc) return null;
    return _toPick(doc);
  }

  /** One-shot full-address refinement once a house number is typed.
   * Uses ``/free`` because:
   *   - ``/suggest`` doesn't full-text-parse "{street} {nr} {city}"
   *     queries, so it returns either nothing or a wrong match.
   *   - the ``/suggest`` + ``/lookup-by-id`` two-stage pattern
   *     turns out to be slower than a single ``/free`` round-trip.
   * ``/free`` is the slowest endpoint per request but still wins on
   * total latency for this lookup. */
  async function lookup(query: string): Promise<LocationPick | null> {
    const trimmed = query.trim();
    if (trimmed.length < 3) return null;
    const doc = await pdokFree(trimmed, { fq: "type:adres", fl: FULL_FL });
    if (!doc) return null;
    return _toPick(doc);
  }

  return { results, searching, search, pick, lookup };
}
