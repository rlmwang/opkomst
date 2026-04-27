import { ref } from "vue";

export interface CitySuggestion {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
}

const SUGGEST_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/suggest";
const LOOKUP_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/lookup";

const RESULT_LIMIT = 8;

interface PdokDoc {
  id: string;
  weergavenaam: string;
  woonplaatsnaam?: string;
  centroide_ll?: string;
}

interface PdokResponse {
  response: { docs: PdokDoc[] };
}

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

let _abort: AbortController | null = null;

export function useCitySuggest() {
  // Each suggestion lacks coords (PDOK ``suggest`` only returns
  // ``id`` + ``weergavenaam``); coords come from a per-pick
  // ``/lookup`` round-trip in ``resolve()``.
  const results = ref<{ id: string; name: string }[]>([]);

  async function search(query: string): Promise<void> {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      results.value = [];
      return;
    }
    if (_abort) _abort.abort();
    _abort = new AbortController();
    try {
      const params = new URLSearchParams({
        q: trimmed,
        fq: "type:woonplaats",
        rows: String(RESULT_LIMIT),
      });
      const resp = await fetch(`${SUGGEST_URL}?${params.toString()}`, { signal: _abort.signal });
      if (!resp.ok) {
        results.value = [];
        return;
      }
      const data = (await resp.json()) as PdokResponse;
      // PDOK's ``weergavenaam`` for ``type:woonplaats`` is
      // ``"{city}, {municipality}, {province}"``. For most Dutch
      // cities the three are identical (Utrecht / Utrecht /
      // Utrecht), which is silly noise in a dropdown. Take the
      // first segment — it's the city name.
      results.value = data.response.docs.map((d) => ({
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
    const params = new URLSearchParams({ id, fl: "id,weergavenaam,centroide_ll" });
    const resp = await fetch(`${LOOKUP_URL}?${params.toString()}`);
    if (!resp.ok) return null;
    const data = (await resp.json()) as PdokResponse;
    const doc = data.response.docs[0];
    if (!doc) return null;
    const point = _parsePoint(doc.centroide_ll);
    if (!point) return null;
    return { id, name, latitude: point.lat, longitude: point.lon };
  }

  return { results, search, resolve };
}
