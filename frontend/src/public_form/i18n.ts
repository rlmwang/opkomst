/**
 * Form-specific strings for the public form mini-app. The shared page
 * chrome (loading / unavailable / load-failed / submit / pseudonym /
 * disclosure) lives in ``@/public_shared/strings``; only the bits
 * unique to a questionnaire live here.
 */

import type { Locale } from "@/public_shared/strings";

export interface FormStrings {
  required: string;
  /** What a number question will accept, in words: the bounds it sits
   *  between and how far off an answer may be. Null when it says
   *  neither, which is a box that takes any whole number. The unit is
   *  not repeated here, it is already beside the box. */
  range: (min: number | null, max: number | null, tolerance: number | null, step: number | null) => string | null;
  missingRequiredPrefix: string;
  withdrawConfirm: string;
  withdrawn: string;
}

const dict: Record<Locale, FormStrings> = {
  nl: {
    required: "verplicht",
    range: (min, max, tolerance, step) => {
      const named = step && step > 1 ? `stapgrootte ${step}` : null;
      const bounds =
        min !== null && max !== null
          ? `tussen ${min} en ${max}`
          : min !== null
            ? `${min} of meer`
            : max !== null
              ? `${max} of minder`
              : null;
      // A margin is worth saying: it is the rule the answer is marked
      // by, not the answer.
      const margin = tolerance ? `je mag er ${tolerance} naast zitten` : null;
      return [named, bounds, margin].filter(Boolean).join(", ") || null;
    },
    missingRequiredPrefix: "Vul deze verplichte vraag in:",
    withdrawConfirm: "Je reactie intrekken? Je antwoorden worden verwijderd.",
    withdrawn: "Je reactie is ingetrokken.",
  },
  en: {
    required: "required",
    range: (min, max, tolerance, step) => {
      const named = step && step > 1 ? `step size ${step}` : null;
      const bounds =
        min !== null && max !== null
          ? `between ${min} and ${max}`
          : min !== null
            ? `${min} or more`
            : max !== null
              ? `${max} or less`
              : null;
      const margin = tolerance ? `you can be ${tolerance} off` : null;
      return [named, bounds, margin].filter(Boolean).join(", ") || null;
    },
    missingRequiredPrefix: "Please answer this required question:",
    withdrawConfirm: "Withdraw your response? Your answers will be deleted.",
    withdrawn: "Your response has been withdrawn.",
  },
};

export function formStrings(locale: Locale): FormStrings {
  return dict[locale];
}
