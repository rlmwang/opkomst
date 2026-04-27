import { useI18n } from "vue-i18n";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { useToasts } from "@/lib/toasts";

/** Copy the public sign-up URL or the QR PNG to the clipboard,
 * with brand-consistent toast feedback. The clipboard API is
 * unavailable on insecure origins and on some browsers without a
 * user gesture — failures are surfaced as a warn for the QR (where
 * fallback isn't obvious) and silently swallowed for the link
 * (where the user can still long-press the URL to copy manually). */
export function useEventClipboard() {
  const toasts = useToasts();
  const { t } = useI18n();

  async function copyLink(slug: string) {
    try {
      await navigator.clipboard.writeText(publicEventUrl(slug));
      toasts.success(t("event.share.linkCopied"));
    } catch {
      /* clipboard unavailable — user can copy the visible URL by hand */
    }
  }

  async function copyQr(slug: string) {
    try {
      const resp = await fetch(eventQrUrl(slug));
      const blob = await resp.blob();
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      toasts.success(t("event.share.qrCopied"));
    } catch {
      toasts.warn(t("event.share.qrCopyFail"));
    }
  }

  return { copyLink, copyQr };
}
