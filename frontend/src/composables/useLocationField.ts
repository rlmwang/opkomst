/**
 * Shared location field for organiser forms (events, datepolls).
 *
 * Holds the free-text ``location`` plus the resolved ``latitude`` /
 * ``longitude``, and derives the geocoder ``chapterBias`` from the
 * selected chapter's city so ``LocationPicker``'s autocomplete favours
 * results near the chapter. Both the event form and the datepoll
 * editor wire ``LocationPicker`` to this, so the state shape +
 * coords/bias logic lives in one place.
 */
import { computed, ref } from "vue";

interface BiasChapter {
  id: string;
  city_lat?: number | null;
  city_lon?: number | null;
}

export function useLocationField(chapterId: () => string | null, chapters: () => BiasChapter[]) {
  const location = ref("");
  const latitude = ref<number | null>(null);
  const longitude = ref<number | null>(null);

  // Bias the geocoder toward the chapter's city (null when no chapter
  // is picked yet → unbiased search).
  const chapterBias = computed<{ lat: number | null; lon: number | null }>(() => {
    const cid = chapterId();
    if (!cid) return { lat: null, lon: null };
    const c = chapters().find((x) => x.id === cid);
    return { lat: c?.city_lat ?? null, lon: c?.city_lon ?? null };
  });

  /** Handler for ``LocationPicker``'s ``@update:coords``. */
  function setCoords(coords: { latitude: number | null; longitude: number | null }): void {
    latitude.value = coords.latitude;
    longitude.value = coords.longitude;
  }

  /** Load all three at once (from an existing entity or a draft). */
  function set(loc: string | null, lat: number | null, lon: number | null): void {
    location.value = loc ?? "";
    latitude.value = lat;
    longitude.value = lon;
  }

  return { location, latitude, longitude, chapterBias, setCoords, set };
}
