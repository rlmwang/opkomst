import { choreQrUrl, publicChoreUrl } from "@/lib/chore-urls";
import { useShareClipboard } from "@/composables/useShareClipboard";

/** Copy the public enrol URL or the QR PNG for a roster. Thin wrapper
 * around the shared share-clipboard helper. */
export function useChoresClipboard() {
  return useShareClipboard({
    publicUrlFor: publicChoreUrl,
    qrUrlFor: choreQrUrl,
    copyPrefix: "chore.share",
  });
}
