/** Public fill-out URL for a form slug. Anyone with this URL can
 *  submit; the slug grants access on its own (no token). */
export function publicFormUrl(slug: string): string {
  return `${window.location.origin}/f/${slug}`;
}

/** SVG endpoint for the form's QR code. Same-origin so the image
 *  inherits whatever auth state the dashboard already has. */
export function formQrUrl(slug: string): string {
  return `/api/v1/forms/by-slug/${slug}/qr.svg`;
}
