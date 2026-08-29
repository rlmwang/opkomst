import { t, te } from "@/i18n.svelte";
import { formsApi, type FormResource } from "@/composables/useForms.svelte";

/**
 * The copy lookup for the four organiser pages the forms table's
 * products share.
 *
 * ``<resource>.<key>`` when the product defines it, ``form.<key>``
 * otherwise: the products share every string that is not about what
 * makes them different. A questionnaire is the base vocabulary, so its
 * own resource resolves to itself either way.
 *
 * This exists as one helper rather than one copy per page because the
 * fallback is silent by design: a missing key lands on the
 * questionnaire's word and reads as a bug in the wrong product's
 * language. Eight of them shipped that way on the quiz. The list of
 * keys that are allowed to fall through is enumerated and tested in
 * ``src/__tests__/form-copy.test.ts``.
 */
export function formText(): {
  resource: FormResource;
  isQuiz: boolean;
  isCompass: boolean;
  L: (key: string, params?: Record<string, unknown>) => string;
} {
  const resource = formsApi().resource;
  const L = (key: string, params?: Record<string, unknown>): string => {
    const own = `${resource}.${key}`;
    return t(te(own) ? own : `form.${key}`, params);
  };
  return { resource, isQuiz: resource === "quiz", isCompass: resource === "compass", L };
}
