/**
 * Shared chrome for the public mini-apps (event sign-up, form,
 * datepoll). These three apps ship as separate bundles without
 * vue-i18n, and used to each re-declare the page chrome — header,
 * language switch, "no longer available" / error screens, the
 * open-source disclosure — which drifted apart. This module is the
 * single source for that chrome: copy that is identical across the
 * three (loading / unavailable / load-failed / submit / pseudonym /
 * disclosure) lives here; each app keeps only its own
 * entity-specific strings.
 */

export type Locale = "nl" | "en";

export const GITHUB_URL = "https://github.com/rlmwang/opkomst";

export interface ChromeStrings {
  loading: string;
  /** Shown for an unknown / archived / expired public link — one
   *  wording for all three entities so the false-url page is
   *  identical everywhere. */
  unavailable: string;
  loadFailed: string;
  /** Optional pseudonym field — "a name, real or not". */
  displayName: string;
  submit: string;
  submitting: string;
  submitFail: string;
  thanks: string;
  explainerTitle: string;
  explainerBody: string;
  explainerLink: string;
  imageCredit: string;
  editPrompt: string;
  editWarning: string;
  copy: string;
  copied: string;
}

const chrome: Record<Locale, ChromeStrings> = {
  nl: {
    loading: "Laden…",
    unavailable: "Deze link is niet meer beschikbaar.",
    loadFailed: "Kon de pagina niet laden",
    displayName: "(Schuil)naam",
    submit: "Versturen",
    submitting: "Versturen…",
    submitFail: "Versturen mislukt",
    thanks: "Bedankt!",
    explainerTitle: "Privacy & open source",
    explainerBody: "We slaan geen e-mailadres of tracking op. De code is open source:",
    explainerLink: "bekijk de broncode",
    imageCredit: "Ontwerp:",
    editPrompt: "Wil je dit later aanpassen? Bewaar dan deze link:",
    editWarning: "Sla 'm op voordat je deze pagina sluit, want we kunnen de link niet opnieuw sturen.",
    copy: "Kopiëren",
    copied: "Gekopieerd",
  },
  en: {
    loading: "Loading…",
    unavailable: "This link is no longer available.",
    loadFailed: "Could not load the page",
    displayName: "(Pseudo)name",
    submit: "Submit",
    submitting: "Submitting…",
    submitFail: "Submitting failed",
    thanks: "Thank you!",
    explainerTitle: "Privacy & open source",
    explainerBody: "We store no email address and no tracking. The code is open source:",
    explainerLink: "view the source",
    imageCredit: "Design:",
    editPrompt: "Want to change this later? Keep this link:",
    editWarning: "Save it before you close this page — we can't send the link again.",
    copy: "Copy",
    copied: "Copied",
  },
};

export function chromeStrings(locale: Locale): ChromeStrings {
  return chrome[locale];
}

/** ``?lang=`` URL override beats the entity's own locale (share with
 *  a friend in another language); otherwise fall back to the entity
 *  locale, default nl. One implementation for all three mini-apps. */
export function pickLocale(entityLocale: string | undefined): Locale {
  const override = new URL(window.location.href).searchParams.get("lang");
  if (override === "nl" || override === "en") return override;
  return entityLocale === "en" ? "en" : "nl";
}
