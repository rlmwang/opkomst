import { locale } from "@/i18n.svelte";
import { resolveText } from "@/public_shared/bilingual";
import type { Locale } from "@/public_shared/strings";

/**
 * Resolve a bilingual entity field (``name_nl``/``name_en``,
 * ``topic_nl``/``topic_en``, ``description_nl``/``description_en``) to
 * the organiser's current language, falling back to the other one when
 * the chosen one is empty.
 *
 * It reads the tracked language, so flipping the header's flag
 * re-renders every entity name and description in the app, exactly the
 * way the public pages react to it. ``null`` when neither language is
 * set; callers render that as empty.
 */
export function lt(nl: string | null | undefined, en: string | null | undefined): string | null {
  return resolveText(nl, en, locale() as Locale);
}
