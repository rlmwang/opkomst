/**
 * The location field the event form and the date poll editor share.
 *
 * Holds the typed address and the coordinates that came back with it,
 * and works out the geocoder's bias from the chapter's own city, so the
 * suggestions favour places near it. Both editors wire
 * ``LocationPicker`` to this, so the shape and the bias live in one
 * place.
 */
interface BiasChapter {
  id: string;
  city_lat?: number | null;
  city_lon?: number | null;
}

export function locationField(chapterId: () => string | null, chapters: () => BiasChapter[]) {
  let location = $state("");
  let latitude = $state<number | null>(null);
  let longitude = $state<number | null>(null);

  return {
    get location(): string {
      return location;
    },
    set location(next: string) {
      location = next;
    },
    get latitude(): number | null {
      return latitude;
    },
    get longitude(): number | null {
      return longitude;
    },

    /** Where to look first. Null on both when no chapter is picked yet,
     *  which is an unbiased search. */
    get bias(): { lat: number | null; lon: number | null } {
      const cid = chapterId();
      if (!cid) return { lat: null, lon: null };
      const c = chapters().find((x) => x.id === cid);
      return { lat: c?.city_lat ?? null, lon: c?.city_lon ?? null };
    },

    /** What ``LocationPicker`` hands back when a suggestion is taken. */
    setCoords(coords: { latitude: number | null; longitude: number | null }): void {
      latitude = coords.latitude;
      longitude = coords.longitude;
    },

    /** All three at once, from a saved row or a draft. */
    set(loc: string | null, lat: number | null, lon: number | null): void {
      location = loc ?? "";
      latitude = lat;
      longitude = lon;
    },
  };
}
