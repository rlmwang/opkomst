import { publicUrl, qrUrl } from "@/lib/public-urls";

/** Public enrol/personal-page URL for a roster slug (``/c/{slug}``). */
export function publicChoreUrl(slug: string): string {
  return publicUrl("c", slug);
}

/** SVG endpoint for the roster's QR code (served by the public router,
 * task 05). */
export function choreQrUrl(slug: string): string {
  return qrUrl("chore", slug);
}
