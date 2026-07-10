import { type Ref, type WritableComputedRef, computed } from "vue";
import { useI18n } from "vue-i18n";

import type { Locale } from "@/public_shared/strings";

/** Two-way binding for one bilingual edit field. Given the ``nl`` and
 *  ``en`` refs, ``active`` reads/writes whichever matches the admin's
 *  current UI language (the top-right toggle), and ``fallback`` is the
 *  other language's current text, for showing as a greyed placeholder.
 *  Flipping the header toggle switches which language you're editing, so
 *  the same title/description controls edit nl then en without any extra
 *  per-field widget. */
export function useBilingualField(
  nl: Ref<string>,
  en: Ref<string>,
): { active: WritableComputedRef<string>; fallback: Ref<string> } {
  const { locale } = useI18n();
  const isEn = (): boolean => (locale.value as Locale) === "en";
  const active = computed<string>({
    get: () => (isEn() ? en.value : nl.value),
    set: (v) => {
      if (isEn()) en.value = v;
      else nl.value = v;
    },
  });
  const fallback = computed<string>(() => (isEn() ? nl.value : en.value));
  return { active, fallback };
}
