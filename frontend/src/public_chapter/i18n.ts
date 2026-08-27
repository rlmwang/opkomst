// Inline strings for the chapter-agenda mini-app (no vue-i18n in the
// public bundles). Chrome strings (image credit, error states) come from
// the shared ``chromeStrings``; only agenda-specific copy lives here.
import type { Locale } from "@/public_shared/strings";

export interface Strings {
  pastHeading: string;
  searchTitles: string;
  searchNoMatches: string;
  signUp: string;
  emptyUpcoming: string;
  notFound: string;
  attendees: (n: number) => string;
  sessionOf: (i: number, n: number) => string;
  sessionOpen: (i: number) => string;
}

const nl: Strings = {
  pastHeading: "Geweest",
  searchTitles: "Zoek op titel",
  searchNoMatches: "Niets gevonden.",
  signUp: "Aanmelden",
  emptyUpcoming: "Er staan nog geen evenementen gepland.",
  notFound: "Deze afdeling bestaat niet (meer).",
  attendees: (n) => `${n} kwamen`,
  sessionOf: (i, n) => `sessie ${i} van ${n}`,
  sessionOpen: (i) => `sessie ${i}`,
};

const en: Strings = {
  pastHeading: "Recently",
  searchTitles: "Search by title",
  searchNoMatches: "Nothing found.",
  signUp: "Sign up",
  emptyUpcoming: "Nothing planned right now.",
  notFound: "This chapter doesn't exist (anymore).",
  attendees: (n) => `${n} came`,
  sessionOf: (i, n) => `session ${i} of ${n}`,
  sessionOpen: (i) => `session ${i}`,
};

export function pickLocale(): Locale {
  // ``?lang=`` override beats the default; chapters are nl-first (the
  // agenda payload carries no per-chapter locale).
  const override = new URL(window.location.href).searchParams.get("lang");
  return override === "en" ? "en" : "nl";
}

export function strings(locale: Locale): Strings {
  return locale === "en" ? en : nl;
}
