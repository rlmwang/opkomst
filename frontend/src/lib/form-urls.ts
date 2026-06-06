/** Public fill-out URL for a form slug. Anyone with this URL can
 *  submit; the slug grants access on its own (no token). */
export function publicFormUrl(slug: string): string {
  return `${window.location.origin}/f/${slug}`;
}
