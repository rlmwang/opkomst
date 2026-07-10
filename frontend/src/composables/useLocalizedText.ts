import { useI18n } from "vue-i18n";

import { resolveText } from "@/public_shared/bilingual";
import type { Locale } from "@/public_shared/strings";

/** Resolve a bilingual entity field (``name_nl``/``name_en``,
 *  ``topic_nl``/``topic_en``, ``description_nl``/``description_en``) to the
 *  admin's current UI language, falling back to the other language when the
 *  chosen one is empty. The returned function reads the reactive vue-i18n
 *  ``locale``, so switching the header language toggle re-renders every
 *  entity name/description shown in the admin, exactly like the public
 *  pages react to the flag. Returns ``null`` when neither language is set;
 *  templates render that as empty and ``v-if``/``v-html`` handle it. */
export function useLocalizedText(): (
  nl: string | null | undefined,
  en: string | null | undefined,
) => string | null {
  const { locale } = useI18n();
  return (nl, en) => resolveText(nl, en, locale.value as Locale);
}
