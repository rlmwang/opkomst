import type { FormResource } from "@/composables/useForms";
import { publicUrl, qrUrl } from "@/lib/public-urls";

/**
 * The public one-letter prefix per product in the forms table. A link
 * says which product it opens before it opens (``docs/design-quizzes.md``);
 * ``k`` is the kompas, whose Dutch name is the one on the page
 * (``docs/design-kompas.md`` part 1.2).
 */
const PUBLIC_PREFIX: Record<FormResource, string> = {
  forms: "f",
  quizzes: "q",
  compasses: "k",
};

/** Public fill-out URL for a slug. Anyone with this URL can submit;
 *  the slug grants access on its own (no token). */
export function publicFormUrl(resource: FormResource, slug: string): string {
  return publicUrl(PUBLIC_PREFIX[resource], slug);
}

/** SVG endpoint for the QR code. The API prefix is the resource name;
 *  the page it points at is the letter above. */
export function formQrUrl(resource: FormResource, slug: string): string {
  return qrUrl(resource, slug);
}
