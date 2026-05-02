/** PDOK Locatieserver client.
 *
 * Three endpoints:
 *  - ``suggest`` — typeahead. Returns ``id`` + ``weergavenaam``
 *    (display string) but no coords; pass a fq filter
 *    (``type:weg``, ``type:adres``, ``type:woonplaats``) to scope
 *    results.
 *  - ``lookup`` — by id. Returns the full document (including
 *    coords) for a previously-suggested row.
 *  - ``free`` — full-text. Slowest per request, but the only
 *    endpoint that parses ``"{street} {nr} {city}"`` queries
 *    correctly, so we use it for the one-shot address refinement.
 *
 * Composables that need the typeahead UX
 * (``useNominatim`` / ``useCitySuggest``) wrap these functions
 * and translate the raw ``PdokDoc`` into their domain shape.
 */

const SUGGEST_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/suggest";
const LOOKUP_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/lookup";
const FREE_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free";

export interface PdokDoc {
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

export interface SuggestOpts {
  /** PDOK fq filter, e.g. ``type:weg`` / ``type:woonplaats``. */
  fq: string;
  /** Max rows. */
  rows?: number;
  /** Soft proximity boost — strongest bias the suggest handler
   * accepts (it doesn't take ``sort=geodist()``). */
  bias?: { lat: number; lon: number };
  /** Abort the in-flight request when the next keystroke fires. */
  signal?: AbortSignal;
}

export async function pdokSuggest(query: string, opts: SuggestOpts): Promise<PdokDoc[]> {
  const params = new URLSearchParams({
    q: query,
    fq: opts.fq,
    rows: String(opts.rows ?? 10),
  });
  if (opts.bias) {
    params.set("lat", String(opts.bias.lat));
    params.set("lon", String(opts.bias.lon));
  }
  const resp = await fetch(`${SUGGEST_URL}?${params.toString()}`, { signal: opts.signal });
  if (!resp.ok) return [];
  const data = (await resp.json()) as PdokResponse;
  return data.response.docs;
}

export async function pdokLookup(id: string, fl?: string): Promise<PdokDoc | null> {
  const params = new URLSearchParams({ id });
  if (fl) params.set("fl", fl);
  const resp = await fetch(`${LOOKUP_URL}?${params.toString()}`);
  if (!resp.ok) return null;
  const data = (await resp.json()) as PdokResponse;
  return data.response.docs[0] ?? null;
}

export async function pdokFree(query: string, opts: { fq: string; fl: string }): Promise<PdokDoc | null> {
  const params = new URLSearchParams({
    q: query,
    fq: opts.fq,
    rows: "1",
    fl: opts.fl,
  });
  const resp = await fetch(`${FREE_URL}?${params.toString()}`);
  if (!resp.ok) return null;
  const data = (await resp.json()) as PdokResponse;
  return data.response.docs[0] ?? null;
}

const POINT_RE = /^POINT\(([-0-9.]+)\s+([-0-9.]+)\)$/;

/** Parse PDOK's ``centroide_ll`` (WKT POINT in EPSG:4326). */
export function parseCentroide(wkt: string | undefined): { lat: number; lon: number } | null {
  if (!wkt) return null;
  const m = POINT_RE.exec(wkt);
  if (!m) return null;
  const lon = Number.parseFloat(m[1]);
  const lat = Number.parseFloat(m[2]);
  if (Number.isNaN(lon) || Number.isNaN(lat)) return null;
  return { lat, lon };
}

/** Helper to manage a single in-flight typeahead controller per
 * caller — every keystroke aborts the previous request so an
 * out-of-order late response doesn't overwrite the latest one. */
export function makeAbortBox(): { next: () => AbortSignal } {
  let current: AbortController | null = null;
  return {
    next: () => {
      if (current) current.abort();
      current = new AbortController();
      return current.signal;
    },
  };
}
