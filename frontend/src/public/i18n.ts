/**
 * Inline i18n for the public sign-up mini-app. Strings copied
 * VERBATIM from ``src/locales/{nl,en}.json`` — the public flow
 * has user-tested copy that must not drift. If a string changes
 * here, also update the JSON for parity (the admin SPA's
 * ``FeedbackPage`` for instance shares some of these via vue-i18n).
 *
 * Keeps the public bundle off vue-i18n (~18 KB gzip we'd be
 * using <1% of).
 */

export type Locale = "nl" | "en";

interface Strings {
  loading: string;
  notFound: string;
  loadFailed: string;
  archived: string;
  addToCalendar: string;
  calIcs: string;
  essentialsTitle: string;
  feedbackTitle: string;
  helpHeading: string;
  displayName: string;
  partySize: string;
  sourcePlaceholder: string;
  emailFor: { reminderAndFeedback: string; reminderOnly: string; feedbackOnly: string };
  emailUses: { reminder: string; feedback: string };
  submit: string;
  submitFail: string;
  fillName: string;
  fillSource: string;
  invalidEmail: string;
  thanks: string;
  thanksBody: string;
  thanksBodyNoEmail: string;
  explainerTitle: string;
  explainerIntro: string;
  explainerEmailIntro: string;
  explainerEmailOutro: string;
  explainerNoEmail: string;
  explainerSource: string;
  explainerLink: string;
}

const dict: Record<Locale, Strings> = {
  nl: {
    loading: "Laden…",
    notFound: "Evenement niet gevonden",
    loadFailed: "Kon evenement niet laden",
    archived: "Dit evenement is gearchiveerd. Je kunt je hier niet meer aanmelden.",
    addToCalendar: "Toevoegen aan agenda",
    calIcs: "ICS-bestand",
    essentialsTitle: "Jouw aanmelding",
    feedbackTitle: "Help ons leren",
    helpHeading: "Ik kan helpen met",
    displayName: "(Schuil)naam",
    partySize: "Aantal personen",
    sourcePlaceholder: "Hoe heb je ons gevonden?",
    emailFor: {
      reminderAndFeedback: "E-mailadres (voor één herinnering + één feedbackmail)",
      reminderOnly: "E-mailadres (voor één herinnering vooraf)",
      feedbackOnly: "E-mailadres (voor één feedbackmail)",
    },
    emailUses: {
      reminder: "Een herinnering, een paar dagen voor het evenement.",
      feedback: "Een korte feedbackmail, kort na afloop.",
    },
    submit: "Aanmelden",
    submitFail: "Aanmelden mislukt",
    fillName: "Vul een naam in",
    fillSource: "Kies hoe je ons hebt gevonden",
    invalidEmail: "Ongeldig e-mailadres",
    thanks: "Bedankt – je aanmelding is binnen.",
    thanksBody:
      "Tot dan! Heb je een mailadres achtergelaten? Dan krijg je de dag erna een korte feedbackmail; daarna gooien we je adres weg.",
    thanksBodyNoEmail: "Tot dan!",
    explainerTitle: "Toelichting",
    explainerIntro:
      "We vragen alleen wat we echt nodig hebben. Een schuilnaam mag – we tellen alleen koppen.",
    explainerEmailIntro:
      "Je mailadres is optioneel. Als je het achterlaat, bewaren we het versleuteld en gebruiken we het voor:",
    explainerEmailOutro: "Zijn alle mails verstuurd, dan gooien we je adres weg.",
    explainerNoEmail: "We vragen verder geen contactgegevens.",
    explainerSource: "De code van deze app is",
    explainerLink: "openbaar in te zien",
  },
  en: {
    loading: "Loading…",
    notFound: "Event not found",
    loadFailed: "Could not load event",
    archived: "This event has been archived. Sign-ups are no longer accepted.",
    addToCalendar: "Add to calendar",
    calIcs: "ICS file",
    essentialsTitle: "Your sign-up",
    feedbackTitle: "Help us learn",
    helpHeading: "I can help with",
    displayName: "(Pseudo)name",
    partySize: "Number of people",
    sourcePlaceholder: "How did you find us?",
    emailFor: {
      reminderAndFeedback: "Email (for one reminder + one feedback message)",
      reminderOnly: "Email (for one reminder before the event)",
      feedbackOnly: "Email (for one feedback message)",
    },
    emailUses: {
      reminder: "One reminder about 3 days before the event starts.",
      feedback: "One short feedback message shortly after the event.",
    },
    submit: "Sign up",
    submitFail: "Sign-up failed",
    fillName: "Fill in a name",
    fillSource: "Pick how you found us",
    invalidEmail: "Invalid email address",
    thanks: "Thanks — we got your sign-up.",
    thanksBody:
      "See you then! If you left an email, you'll get one short feedback question the day after the event. After that we delete your address.",
    thanksBodyNoEmail: "See you then!",
    explainerTitle: "Explainer",
    explainerIntro:
      "We only ask for what we need. Your name can be a pseudonym — it just helps us with the head count.",
    explainerEmailIntro:
      "Your email is optional. If you leave it, we store it encrypted and use it for:",
    explainerEmailOutro:
      "Once every email related to this event has been sent, we permanently delete your address.",
    explainerNoEmail: "We're not asking for any contact details for this event.",
    explainerSource: "The full source code of this app is",
    explainerLink: "openly available",
  },
};

export function pickLocale(eventLocale: string | undefined): Locale {
  // ``?lang=`` URL override beats the event's own locale; useful
  // for share-with-an-English-speaking-friend cases without
  // touching the organiser-side setting.
  const url = new URL(window.location.href);
  const override = url.searchParams.get("lang");
  if (override === "nl" || override === "en") return override;
  return eventLocale === "en" ? "en" : "nl";
}

export function strings(locale: Locale): Strings {
  return dict[locale];
}
