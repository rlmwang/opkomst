import { publicUrl, qrUrl } from "@/lib/public-urls";

/** Public sign-up URL for an event slug. The QR code points here. */
export function publicEventUrl(slug: string): string {
  return publicUrl("e", slug);
}

/** SVG endpoint for the event's QR code. */
export function eventQrUrl(slug: string): string {
  return qrUrl("events", slug);
}
