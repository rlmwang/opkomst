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
/** Where "something is wrong / I have an idea" goes: a new issue on the
 *  same repository the source link points at. No form of our own to
 *  build, moderate or store, and the report is public the way the code
 *  is. */
export const GITHUB_ISSUE_URL = `${GITHUB_URL}/issues/new`;

export interface ChromeStrings {
  loading: string;
  /** Shown for an unknown / archived / expired public link — one
   *  wording for all three entities so the false-url page is
   *  identical everywhere. */
  unavailable: string;
  loadFailed: string;
  /** Pseudonym field — "a name, real or not"; required on every page. */
  displayName: string;
  /** Shown when the (pseudo)name field is left blank on submit. */
  nameRequired: string;
  /** Shown where Save would be, when the organiser has closed the
   *  answers for changes. */
  answersClosed: string;
  /** Shown when a typed email address is malformed. */
  invalidEmail: string;
  submit: string;
  submitting: string;
  submitFail: string;
  /** Refused because the thing has no places left. Personal accounts
   *  hold a bounded number of people per event, form, poll or roster;
   *  an organisation's has no ceiling, so this never shows there. Said
   *  plainly, and without saying whose account it is or how full. */
  full: string;
  /** The confirmation-card heading, identical across all four entity
   *  types. */
  thanks: string;
  // Edit-mode action bar (shared by every public edit page).
  save: string;
  saved: string;
  revert: string;
  withdraw: string;
  explainerTitle: string;
  explainerBody: string;
  explainerLink: string;
  /** Names the ad slot for screen readers and as the fallback image's
   *  alt text. */
  adLabel: string;
  /** Added to the disclosure only while an ad network is actually
   *  configured. Without one the slot is a static image we host and
   *  ``explainerBody`` is true as written. */
  adDisclosure: string;
  /** What the slot says when it is not showing an ad and there is
   *  nothing to ask for either. */
  /** "Feedback", linked from the disclosure beside the privacy policy:
   *  it opens a new issue on the repository. */
  feedbackLink: string;
  /** The privacy policy, linked from the disclosure on every public
   *  page. */
  privacyLink: string;
  adNone: string;
  /** What the slot says when it is not showing an ad and there is
   *  somewhere to support the project. The two service names on the
   *  buttons are brands and stay in English in both languages. */
  supportHeading: string;
  imageCredit: string;
  editPrompt: string;
  /** The same link when there is nothing left to change: a quiz, or a
   *  form whose organiser has closed the answers. */
  editPromptReadonly: string;
  editWarning: string;
  /** Permanent notice on the edit page once an organiser has copied
   *  (re-minted) this submission's secret link — ``{date}`` is the most
   *  recent copy. Transparency contract: never hidden, never cleared. */
  linkRecovered: string;
  copy: string;
  copied: string;
}

const chrome: Record<Locale, ChromeStrings> = {
  nl: {
    loading: "Laden…",
    unavailable: "Deze link is niet meer beschikbaar.",
    loadFailed: "Kon de pagina niet laden",
    displayName: "(Schuil)naam",
    nameRequired: "Vul een (schuil)naam in.",
    answersClosed: "Aanpassen kan niet meer.",
    invalidEmail: "Ongeldig e-mailadres.",
    submit: "Versturen",
    submitting: "Versturen…",
    submitFail: "Versturen mislukt",
    full: "Dit zit vol. Er zijn geen plekken meer.",
    thanks: "Bedankt!",
    save: "Opslaan",
    saved: "Opgeslagen",
    revert: "Herstellen",
    withdraw: "Afmelden",
    explainerTitle: "Privacy & open source",
    explainerBody: "We slaan geen e-mailadres of tracking op. De code is open source:",
    explainerLink: "bekijk de broncode",
    adLabel: "Advertentie",
    adDisclosure:
      "Op deze pagina staat één advertentie van Google. Die zet cookies, en je kunt zelf kiezen wat je toestaat.",
    feedbackLink: "Feedback",
    privacyLink: "Privacyverklaring",
    adNone: "Geen advertenties",
    supportHeading: "Help je mee dit advertentievrij te houden?",
    imageCredit: "Ontwerp:",
    editPrompt: "Bewaar deze link om dit later aan te passen:",
    editPromptReadonly: "Bewaar deze link om dit later terug te zien:",
    editWarning:
      "Sla 'm op voordat je deze pagina sluit. Kwijt? Een organisator kan een nieuwe maken.",
    linkRecovered:
      "Een organisator heeft op {date} de geheime link van deze inzending gekopieerd (de vorige link verviel daarmee). Niet op jouw verzoek? Meld je dan af en meld je opnieuw aan voor een verse link.",
    copy: "Kopiëren",
    copied: "Gekopieerd",
  },
  en: {
    loading: "Loading…",
    unavailable: "This link is no longer available.",
    loadFailed: "Could not load the page",
    displayName: "(Pseudo)name",
    nameRequired: "Enter a (pseudo)name.",
    answersClosed: "Changes are closed.",
    invalidEmail: "Invalid email address.",
    submit: "Submit",
    submitting: "Submitting…",
    submitFail: "Submitting failed",
    full: "This is full. No more places are available.",
    thanks: "Thank you!",
    save: "Save",
    saved: "Saved",
    revert: "Revert",
    withdraw: "Withdraw",
    explainerTitle: "Privacy & open source",
    explainerBody: "We store no email address and no tracking. The code is open source:",
    explainerLink: "view the source",
    adLabel: "Advertisement",
    adDisclosure:
      "This page carries one advertisement from Google. It sets cookies, and you choose what you allow.",
    feedbackLink: "Feedback",
    privacyLink: "Privacy policy",
    adNone: "No ads",
    supportHeading: "Want to help us keep this ad free?",
    imageCredit: "Design:",
    editPrompt: "Save this link to change this later:",
    editPromptReadonly: "Save this link to see this again later:",
    editWarning: "Save it before you close this page. Lost it? An organiser can mint a new one.",
    linkRecovered:
      "An organiser copied this entry's secret link on {date} (the previous link stopped working). Not at your request? Withdraw and sign up again for a fresh link.",
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
