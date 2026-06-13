/**
 * Datepoll-specific strings for the public datepoll mini-app. The
 * shared page chrome (loading / unavailable / load-failed / submit /
 * pseudonym / disclosure) lives in ``@/public_shared/strings``; only
 * the bits unique to a date poll live here.
 */

import type { Locale } from "@/public_shared/strings";

export interface DatepollStrings {
  intro: string;
  legend: string;
  yes: string;
  maybe: string;
  no: string;
  commentPlaceholder: string;
  pickOne: string;
  thanksBody: string;
}

const dict: Record<Locale, DatepollStrings> = {
  nl: {
    intro: "Tik op een datum om je beschikbaarheid aan te geven.",
    legend: "Tik om te wisselen:",
    yes: "Ja",
    maybe: "Misschien",
    no: "Nee",
    commentPlaceholder: "Opmerking (optioneel)",
    pickOne: "Kies bij minstens één datum je beschikbaarheid.",
    thanksBody: "Je reactie is binnen.",
  },
  en: {
    intro: "Tap a date to set your availability.",
    legend: "Tap to cycle:",
    yes: "Yes",
    maybe: "Maybe",
    no: "No",
    commentPlaceholder: "Comment (optional)",
    pickOne: "Set your availability for at least one date.",
    thanksBody: "Your response is in.",
  },
};

export function datepollStrings(locale: Locale): DatepollStrings {
  return dict[locale];
}

/** Long human-readable date for the list rows: ``Monday 27 April``. */
export function formatLongDate(iso: string, locale: Locale): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale === "en" ? "en-GB" : "nl-NL", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}
