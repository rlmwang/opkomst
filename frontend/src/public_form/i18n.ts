/**
 * Inline i18n for the public form mini-app. Strings live here
 * rather than in ``src/locales/{nl,en}.json`` because the mini-
 * app deliberately ships without vue-i18n (~18 KB gzip we'd be
 * using ~0% of). The admin SPA's ``forms.public.*`` keys cover
 * the same surface for the rare in-app "preview" scenario; keep
 * the wording in lockstep.
 */

export type Locale = "nl" | "en";

interface Strings {
  loading: string;
  unavailable: string;
  loadFailed: string;
  submit: string;
  submitting: string;
  submitFail: string;
  thanks: string;
  thanksBody: string;
  required: string;
  missingRequiredPrefix: string;
}

const dict: Record<Locale, Strings> = {
  nl: {
    loading: "Laden…",
    unavailable: "Deze vragenlijst is niet meer beschikbaar.",
    loadFailed: "Kon de vragenlijst niet laden.",
    submit: "Versturen",
    submitting: "Versturen…",
    submitFail: "Versturen mislukt. Probeer het opnieuw.",
    thanks: "Bedankt!",
    thanksBody: "Je inzending is opgeslagen.",
    required: "verplicht",
    missingRequiredPrefix: "Vul deze verplichte vraag in:",
  },
  en: {
    loading: "Loading…",
    unavailable: "This form is no longer available.",
    loadFailed: "Could not load the form.",
    submit: "Submit",
    submitting: "Submitting…",
    submitFail: "Submitting failed. Please try again.",
    thanks: "Thank you!",
    thanksBody: "Your response has been recorded.",
    required: "required",
    missingRequiredPrefix: "Please answer this required question:",
  },
};

export function pickLocale(formLocale: string | undefined): Locale {
  // ``?lang=`` URL override beats the form's own locale; useful
  // for share-with-an-English-speaking-friend cases without
  // touching the organiser-side setting. Mirrors the events
  // mini-app's behaviour.
  const url = new URL(window.location.href);
  const override = url.searchParams.get("lang");
  if (override === "nl" || override === "en") return override;
  return formLocale === "en" ? "en" : "nl";
}

export function strings(locale: Locale): Strings {
  return dict[locale];
}
