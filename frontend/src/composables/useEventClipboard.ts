import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { useShareClipboard } from "@/composables/useShareClipboard";

/** Copy the public sign-up URL or the QR PNG for an event. Thin
 * wrapper around the shared share-clipboard helper — Events and
 * Forms use identical browser logic for the copy/raster/download
 * dance, differing only in URL builders and locale prefix. */
export function useEventClipboard() {
  return useShareClipboard({
    publicUrlFor: publicEventUrl,
    qrUrlFor: eventQrUrl,
    copyPrefix: "event.share",
  });
}
