import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useShareClipboard } from "@/composables/useShareClipboard";

/** Copy the public fill-out URL or the QR PNG for a form. Thin
 * wrapper around the shared share-clipboard helper. */
export function useFormClipboard() {
  return useShareClipboard({
    publicUrlFor: publicFormUrl,
    qrUrlFor: formQrUrl,
    copyPrefix: "forms.share",
  });
}
