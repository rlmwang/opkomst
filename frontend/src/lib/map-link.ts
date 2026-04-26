/**
 * Build a link to an OpenStreetMap page for a given event location.
 *
 * If we have coordinates, drop a marker pin at zoom 18; otherwise fall
 * back to OSM's search form for the free-text location string. We
 * deliberately stay on openstreetmap.org rather than handing off to
 * Google / Apple maps — same reason we use OSM tiles for the inline
 * preview.
 */
export function mapLink(opts: {
  location: string;
  latitude: number | null;
  longitude: number | null;
}): string {
  if (opts.latitude !== null && opts.longitude !== null) {
    const lat = opts.latitude;
    const lon = opts.longitude;
    return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=18/${lat}/${lon}`;
  }
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(opts.location)}`;
}
