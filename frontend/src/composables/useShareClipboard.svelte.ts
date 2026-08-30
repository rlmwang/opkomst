import { t } from "@/i18n.svelte";
import { useToasts } from "@/lib/toasts";

/**
 * Copy a public URL, or copy the QR as an image.
 *
 * The browser behaviour is identical for events, forms, date polls and
 * rosters; what differs is the two URL builders and the i18n prefix the
 * toasts read. Each caller passes its own, so there is one copy of the
 * rasterising and the fallbacks.
 *
 * The clipboard is unavailable on an insecure origin and on some
 * browsers without a user gesture. A failed QR copy falls back to a
 * download and finally to a warning; a failed link copy says nothing,
 * because the URL is on screen and can be copied by hand.
 */
export interface ShareUrlBuilders {
  /** The public URL for a slug, e.g. ``/e/{slug}``. */
  publicUrlFor: (slug: string) => string;
  /** The QR endpoint for a slug. */
  qrUrlFor: (slug: string) => string;
  /** i18n prefix holding ``linkCopied``, ``qrCopied``, ``qrDownloaded``
   *  and ``qrCopyFail``, e.g. ``"event.share"``. */
  copyPrefix: string;
}

export function shareClipboard(b: ShareUrlBuilders) {
  const toasts = useToasts();

  async function copyLink(slug: string) {
    try {
      await navigator.clipboard.writeText(b.publicUrlFor(slug));
      toasts.success(t(`${b.copyPrefix}.linkCopied`));
    } catch {
      /* clipboard unavailable; the URL is on screen to copy by hand */
    }
  }

  async function copyQr(slug: string) {
    // The endpoint serves SVG, which keeps the server free of an image
    // library, but most paste targets take raster only. Rasterise here
    // at 512px so a pasted QR is crisp whatever the SVG's own size.
    //
    // Support is uneven: desktop Chrome, Edge and Safari take
    // ``image/png`` in a ``ClipboardItem``; Firefox on Android rejects
    // the write although ``ClipboardItem`` exists. iOS Safari wants the
    // ``ClipboardItem`` built synchronously inside the gesture handler,
    // so the Blob goes in as a promise, which the spec allows and which
    // works on both. Where the write cannot happen at all, the PNG is
    // downloaded instead: one more step, but the image is in hand.
    const buildPng = async (): Promise<Blob> => {
      const svg = await (await fetch(b.qrUrlFor(slug))).text();
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
          canvas.toBlob((png) => (png ? resolve(png) : reject(new Error("toBlob null"))), "image/png"),
        );
      } finally {
        URL.revokeObjectURL(url);
      }
    };

    if ("ClipboardItem" in window && navigator.clipboard?.write) {
      try {
        const blobPromise = buildPng();
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blobPromise })]);
        toasts.success(t(`${b.copyPrefix}.qrCopied`));
        return;
      } catch {
        // fall through to the download
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
      toasts.success(t(`${b.copyPrefix}.qrDownloaded`));
    } catch {
      toasts.warn(t(`${b.copyPrefix}.qrCopyFail`));
    }
  }

  return { copyLink, copyQr };
}
