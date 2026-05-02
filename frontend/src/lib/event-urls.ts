/** Public sign-up URL for an event slug. The QR code points here. */
export function publicEventUrl(slug: string): string {
  return `${window.location.origin}/e/${slug}`;
}

/** SVG endpoint for the event's QR code. Same origin so the image
 * inherits whatever auth state the dashboard already has. */
export function eventQrUrl(slug: string): string {
  return `/api/v1/events/by-slug/${slug}/qr.svg`;
}
