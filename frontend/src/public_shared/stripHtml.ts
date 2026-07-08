// Flatten a sanitized rich-text body to plain text for the surfaces that
// take a string, not HTML (the native Web Share sheet). Uses the
// browser's own parser, so no sanitizer or markdown dependency is pulled
// into the deliberately-lean public bundles. The input is already
// server-sanitized; this only reads ``textContent``, never executes it.
export function stripHtml(html: string | null | undefined): string {
  if (!html) return "";
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent ?? "").trim();
}
