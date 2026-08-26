import { publicUrl, qrUrl } from "@/lib/public-urls";

/** Public fill-out URL for a form slug. Anyone with this URL can
 *  submit; the slug grants access on its own (no token). */
export function publicFormUrl(slug: string): string {
  return publicUrl("f", slug);
}

/** SVG endpoint for the form's QR code. */
export function formQrUrl(slug: string): string {
  return qrUrl("forms", slug);
}

/** The same two, for the other product in the forms table. A quiz has
 *  its own public prefix so a link says which it is before it opens
 *  (``docs/design-quizzes.md``). */
export function publicQuizUrl(slug: string): string {
  return publicUrl("q", slug);
}

export function quizQrUrl(slug: string): string {
  return qrUrl("quizzes", slug);
}
