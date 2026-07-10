import type { Locale } from "./strings";

/** Resolve a bilingual entity field to the visitor's chosen language,
 *  falling back to the other language when the chosen one is empty. The
 *  backend stores a blank field as ``null`` (never ``""``), so a simple
 *  truthiness fallback is correct here. Returns ``null`` when neither
 *  language has content. Reactive callers pass ``locale.value`` so the
 *  flag toggle re-renders the content live, the same way it already
 *  re-renders the UI chrome. */
export function resolveText(
  nl: string | null | undefined,
  en: string | null | undefined,
  locale: Locale,
): string | null {
  const primary = locale === "en" ? en : nl;
  const fallback = locale === "en" ? nl : en;
  return primary || fallback || null;
}
