/** Public-surface URL builders, shared by every chapter-scoped
 *  resource that has a public-by-slug page (events, forms,
 *  datepolls). The per-resource helpers (``lib/event-urls.ts`` etc.)
 *  delegate here so the URL shape lives in one place. */

/** Public page for a slug under a one/two-letter prefix
 *  (``e`` / ``f`` / ``d``). Anyone with this URL can view/submit;
 *  the slug grants access on its own (no token). */
export function publicUrl(prefix: string, slug: string): string {
  return `${window.location.origin}/${prefix}/${slug}`;
}

/** Same-origin SVG endpoint for a resource's QR code. Same origin so
 *  the image inherits whatever auth state the dashboard already has. */
export function qrUrl(resource: string, slug: string): string {
  return `/api/v1/${resource}/by-slug/${slug}/qr.svg`;
}
