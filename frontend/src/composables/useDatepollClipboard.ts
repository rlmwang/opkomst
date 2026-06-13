import { useShareClipboard } from "@/composables/useShareClipboard";
import { datepollQrUrl, publicDatepollUrl } from "@/lib/datepoll-urls";

/** Copy the public fill-out URL or the QR PNG for a datepoll. Thin
 * wrapper around the shared share-clipboard helper. */
export function useDatepollClipboard() {
  return useShareClipboard({
    publicUrlFor: publicDatepollUrl,
    qrUrlFor: datepollQrUrl,
    copyPrefix: "datepolls.share",
  });
}
