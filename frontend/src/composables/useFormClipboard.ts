import { formQrUrl, publicFormUrl, publicQuizUrl, quizQrUrl } from "@/lib/form-urls";
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

/** The same for a quiz, whose public page and QR live under their own
 *  prefix. */
export function useQuizClipboard() {
  return useShareClipboard({
    publicUrlFor: publicQuizUrl,
    qrUrlFor: quizQrUrl,
    copyPrefix: "forms.share",
  });
}
