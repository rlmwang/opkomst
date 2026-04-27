import { ref } from "vue";

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

const SUGGEST_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/suggest";
const LOOKUP_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/lookup";
const FREE_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free";

const RESULT_LIMIT = 10;
const FULL_FL = "id,weergavenaam,straatnaam,woonplaatsnaam,gemeentenaam,centroide_ll";

interface PdokDoc {
  id: string;
  weergavenaam: string;
  straatnaam?: string;
  woonplaatsnaam?: string;
  gemeentenaam?: string;
  centroide_ll?: string;
}

interface PdokResponse {
  response: { docs: PdokDoc[] };
}

let _abort: AbortController | null = null;

const POINT_RE = /^POINT\(([-0-9.]+)\s+([-0-9.]+)\)$/;

function _parsePoint(wkt: string | undefined): { lat: number; lon: number } | null {
  if (!wkt) return null;
  const m = POINT_RE.exec(wkt);
  if (!m) return null;
  const lon = Number.parseFloat(m[1]);
  const lat = Number.parseFloat(m[2]);
  if (Number.isNaN(lon) || Number.isNaN(lat)) return null;
  return { lat, lon };
}

async function _suggest(
  query: string,
  filter: string,
  rows: number,
  signal: AbortSignal,
  bias?: { lat: number; lon: number },
): Promise<PdokDoc[]> {
  const params = new URLSearchParams({ q: query, fq: filter, rows: String(rows) });
  if (bias) {
    // PDOK accepts ``lat``/``lon`` here as a soft proximity boost
    // and that's the strongest bias we can apply on the suggest
    // handler — it doesn't accept ``sort=`` (no ``geodist()``) and
    // the alternative ``free`` endpoint doesn't do prefix matching,
    // which a typeahead can't do without. Live with the soft boost.
    params.set("lat", String(bias.lat));
    params.set("lon", String(bias.lon));
  }
  const resp = await fetch(`${SUGGEST_URL}?${params.toString()}`, { signal });
  if (!resp.ok) return [];
  const data = (await resp.json()) as PdokResponse;
  return data.response.docs;
}

async function _lookupById(id: string): Promise<PdokDoc | null> {
  const params = new URLSearchParams({ id, fl: FULL_FL });
  const resp = await fetch(`${LOOKUP_URL}?${params.toString()}`);
  if (!resp.ok) return null;
  const data = (await resp.json()) as PdokResponse;
  return data.response.docs[0] ?? null;
}

function _toPick(doc: PdokDoc): LocationPick | null {
  const point = _parsePoint(doc.centroide_ll);
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

  async function search(query: string, bias?: { lat: number; lon: number }): Promise<void> {
    const trimmed = query.trim();
    if (trimmed.length < 3) {
      results.value = [];
      return;
    }

    if (_abort) _abort.abort();
    _abort = new AbortController();

    searching.value = true;
    try {
      const docs = await _suggest(trimmed, "type:weg", RESULT_LIMIT, _abort.signal, bias);
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
    const doc = await _lookupById(r.id);
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
    const params = new URLSearchParams({
      q: trimmed,
      fq: "type:adres",
      rows: "1",
      fl: FULL_FL,
    });
    const resp = await fetch(`${FREE_URL}?${params.toString()}`);
    if (!resp.ok) return null;
    const data = (await resp.json()) as PdokResponse;
    const doc = data.response.docs[0];
    if (!doc) return null;
    return _toPick(doc);
  }

  return { results, searching, search, pick, lookup };
}
