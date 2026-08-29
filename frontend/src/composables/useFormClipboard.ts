import type { FormResource } from "@/composables/useForms";
import { useShareClipboard } from "@/composables/useShareClipboard";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";

/** Copy the public fill-out URL or the QR PNG for one of the forms
 *  table's products. Thin wrapper around the shared share-clipboard
 *  helper; the resource decides which public prefix the copied link
 *  carries. */
export function useFormClipboard(resource: FormResource) {
  return useShareClipboard({
    publicUrlFor: (slug: string) => publicFormUrl(resource, slug),
    qrUrlFor: (slug: string) => formQrUrl(resource, slug),
    copyPrefix: "form.share",
  });
}
