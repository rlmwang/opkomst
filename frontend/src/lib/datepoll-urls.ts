import { publicUrl, qrUrl } from "@/lib/public-urls";

/** Public fill-out URL for a datepoll slug. */
export function publicDatepollUrl(slug: string): string {
  return publicUrl("d", slug);
}

/** SVG endpoint for the datepoll's QR code. */
export function datepollQrUrl(slug: string): string {
  return qrUrl("datepolls", slug);
}
