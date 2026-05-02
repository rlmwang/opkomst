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
    // The endpoint serves SVG (server stays PIL-free) but most
    // clipboard targets — Slack, Word, image inputs — only accept
    // raster. Rasterise client-side via a canvas at 512px so
    // pasted QRs are crisp regardless of the SVG's intrinsic size.
    //
    // Browser support is uneven: desktop Chrome/Edge/Safari accept
    // ``image/png`` in ``ClipboardItem``; Firefox Android (and
    // some other mobile browsers) reject the write even though
    // ``ClipboardItem`` itself is defined. iOS Safari additionally
    // requires the ``ClipboardItem`` to be constructed
    // synchronously inside the user-gesture handler — so we pass
    // the Blob as a Promise (spec-compliant; works on iOS and
    // desktop). When the clipboard write rejects on a browser
    // that simply can't write images, fall back to triggering a
    // download of the PNG: the user still gets a saveable image
    // they can attach or share, just one extra step.
    const buildPng = async (): Promise<Blob> => {
      const svg = await (await fetch(eventQrUrl(slug))).text();
      const svgBlob = new Blob([svg], { type: "image/svg+xml" });
      const url = URL.createObjectURL(svgBlob);
      try {
        const img = new Image();
        img.src = url;
        await img.decode();
        const size = 512;
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("no 2d context");
        ctx.drawImage(img, 0, 0, size, size);
        return await new Promise<Blob>((resolve, reject) =>
          canvas.toBlob(
            (b) => (b ? resolve(b) : reject(new Error("toBlob null"))),
            "image/png",
          ),
        );
      } finally {
        URL.revokeObjectURL(url);
      }
    };

    if ("ClipboardItem" in window && navigator.clipboard?.write) {
      try {
        const blobPromise = buildPng();
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blobPromise })]);
        toasts.success(t("event.share.qrCopied"));
        return;
      } catch {
        // fall through to download
      }
    }

    try {
      const png = await buildPng();
      const url = URL.createObjectURL(png);
      const a = document.createElement("a");
      a.href = url;
      a.download = `qr-${slug}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toasts.success(t("event.share.qrDownloaded"));
    } catch {
      toasts.warn(t("event.share.qrCopyFail"));
    }
  }

  return { copyLink, copyQr };
}
