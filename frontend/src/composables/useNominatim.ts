import { ref } from "vue";

export interface NominatimResult {
  display_name: string;
  lat: string;
  lon: string;
  place_id: number;
}

export interface LocationPick {
  display_name: string;
  latitude: number;
  longitude: number;
}

const ENDPOINT = "https://nominatim.openstreetmap.org/search";

// Nominatim's public instance asks for an identifying User-Agent / Referer.
// Browsers set Referer automatically; we add an `email` query parameter
// (their secondary identification mechanism) so they can reach out before
// rate-limiting if we ever misbehave. The address itself never leaves
// localStorage / form state — only the query string the user typed.
const CONTACT_PARAM = "email=opkomst@flatwork.nl";

let _abort: AbortController | null = null;

export function useNominatim() {
  const results = ref<NominatimResult[]>([]);
  const searching = ref(false);

  async function search(query: string): Promise<void> {
    const trimmed = query.trim();
    if (trimmed.length < 3) {
      results.value = [];
      return;
    }

    // Cancel any in-flight request — only the latest keystroke matters.
    if (_abort) _abort.abort();
    _abort = new AbortController();

    searching.value = true;
    try {
      const url = `${ENDPOINT}?q=${encodeURIComponent(trimmed)}&format=json&limit=6&addressdetails=0&${CONTACT_PARAM}`;
      const resp = await fetch(url, { signal: _abort.signal, headers: { "Accept-Language": "nl,en" } });
      if (!resp.ok) {
        results.value = [];
        return;
      }
      results.value = (await resp.json()) as NominatimResult[];
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        results.value = [];
      }
    } finally {
      searching.value = false;
    }
  }

  function pick(r: NominatimResult): LocationPick {
    return {
      display_name: r.display_name,
      latitude: Number.parseFloat(r.lat),
      longitude: Number.parseFloat(r.lon),
    };
  }

  return { results, searching, search, pick };
}
