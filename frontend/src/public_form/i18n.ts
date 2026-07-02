/**
 * Form-specific strings for the public form mini-app. The shared page
 * chrome (loading / unavailable / load-failed / submit / pseudonym /
 * disclosure) lives in ``@/public_shared/strings``; only the bits
 * unique to a questionnaire live here.
 */

import type { Locale } from "@/public_shared/strings";

export interface FormStrings {
  thanksBody: string;
  required: string;
  missingRequiredPrefix: string;
  withdrawConfirm: string;
  withdrawn: string;
}

const dict: Record<Locale, FormStrings> = {
  nl: {
    thanksBody: "Je inzending is binnen.",
    required: "verplicht",
    missingRequiredPrefix: "Vul deze verplichte vraag in:",
    withdrawConfirm: "Je reactie intrekken? Je antwoorden worden verwijderd.",
    withdrawn: "Je reactie is ingetrokken.",
  },
  en: {
    thanksBody: "Your response is in.",
    required: "required",
    missingRequiredPrefix: "Please answer this required question:",
    withdrawConfirm: "Withdraw your response? Your answers will be deleted.",
    withdrawn: "Your response has been withdrawn.",
  },
};

export function formStrings(locale: Locale): FormStrings {
  return dict[locale];
}
