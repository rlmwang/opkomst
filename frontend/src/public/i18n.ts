/**
 * Inline i18n for the public sign-up mini-app. Plain-string copy is kept
 * in parity with the ``public`` block of ``src/locales/{nl,en}.json``;
 * the parameterised session labels mirror ``event.occurrences.*`` there.
 * If a string changes here, update the JSON too.
 *
 * Keeps the public bundle off vue-i18n (~18 KB gzip we'd be using <1% of).
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
  /** One per combination of enabled mail channels. The field is only
   *  shown when at least one of them is on, so there is no variant for
   *  "neither". */
  emailPlaceholder: { both: string; reminder: string; feedback: string };
  emailUses: { reminder: string; feedback: string };
  submit: string;
  submitFail: string;
  // Occurrence checklist.
  sessionsTitle: string;
  allUpcoming: string;
  sessionOf: (i: number, n: number) => string;
  sessionOpen: (i: number) => string;
  notYetOpen: string;
  pickSession: string;
  prevMonth: string;
  nextMonth: string;
  pickerExplainer: string;
  reminderOptIn: string;
  reminderOptOut: string;
  // Booking edit.
  bookingSessions: string;
  withdrawConfirm: string;
  /** Appended to the withdraw confirmation when this event still has a
   *  channel switched on. Switching one off deletes its pending
   *  dispatches, so with both off nothing can arrive and the caveat
   *  would be a lie. */
  pendingMailWarning: string;
  withdrawn: string;
  explainerTitle: string;
  explainerIntro: string;
  explainerEmailIntro: string;
  explainerEmailOutro: string;
  explainerSource: string;
  explainerLink: string;
  imageCredit: string;
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
    emailPlaceholder: {
      both: "E-mailadres (optioneel, voor de herinnering en de feedbackmail)",
      reminder: "E-mailadres (optioneel, voor de herinnering)",
      feedback: "E-mailadres (optioneel, voor de feedbackmail)",
    },
    emailUses: {
      reminder: "Een herinnering, een paar dagen voor het evenement.",
      feedback: "Een korte feedbackmail, kort na afloop.",
    },
    submit: "Aanmelden",
    submitFail: "Aanmelden mislukt",
    sessionsTitle: "Voor welke sessies wil je je aanmelden?",
    allUpcoming: "Alle komende sessies",
    sessionOf: (i, n) => `sessie ${i} van ${n}`,
    sessionOpen: (i) => `sessie ${i}`,
    notYetOpen: "nog niet open",
    pickSession: "Kies minstens één sessie",
    prevMonth: "Vorige maand",
    nextMonth: "Volgende maand",
    pickerExplainer: "Tik op de gemarkeerde dagen om je sessies te kiezen.",
    reminderOptIn: "Latere sessies moet je zelf toevoegen wanneer ze verschijnen.",
    reminderOptOut: "Latere sessies moet je zelf laten vallen wanneer ze verschijnen.",
    bookingSessions: "Je sessies",
    withdrawConfirm: "Je voor alle sessies afmelden? Je hele aanmelding wordt verwijderd.",
    pendingMailWarning: "Een al ingeplande herinnering of vragenlijst kan alsnog aankomen.",
    withdrawn: "Je bent afgemeld.",
    explainerTitle: "Privacy & open source",
    explainerIntro:
      "We vragen alleen wat we echt nodig hebben. Een schuilnaam mag, we tellen alleen koppen.",
    explainerEmailIntro:
      "Je mailadres is optioneel. Als je het achterlaat, bewaren we het versleuteld en gebruiken we het voor:",
    explainerEmailOutro: "Zijn alle mails verstuurd, dan gooien we je adres weg.",
    explainerSource: "De code van deze app is",
    explainerLink: "openbaar in te zien",
    imageCredit: "Ontwerp:",
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
    emailPlaceholder: {
      both: "Email (optional, for the reminder and the feedback message)",
      reminder: "Email (optional, for the reminder)",
      feedback: "Email (optional, for the feedback message)",
    },
    emailUses: {
      reminder: "One reminder about 3 days before the event starts.",
      feedback: "One short feedback message shortly after the event.",
    },
    submit: "Sign up",
    submitFail: "Sign-up failed",
    sessionsTitle: "Which sessions do you want to join?",
    allUpcoming: "All upcoming sessions",
    sessionOf: (i, n) => `session ${i} of ${n}`,
    sessionOpen: (i) => `session ${i}`,
    notYetOpen: "not open yet",
    pickSession: "Pick at least one session",
    prevMonth: "Previous month",
    nextMonth: "Next month",
    pickerExplainer: "Tap the highlighted days to choose your sessions.",
    reminderOptIn: "You'll need to add later sessions yourself as they appear.",
    reminderOptOut: "You'll need to drop later sessions yourself as they appear.",
    bookingSessions: "Your sessions",
    withdrawConfirm: "Withdraw from every session? Your whole sign-up will be removed.",
    pendingMailWarning: "A reminder or feedback email that's already scheduled may still arrive.",
    withdrawn: "You've withdrawn.",
    explainerTitle: "Privacy & open source",
    explainerIntro:
      "We only ask for what we need. Your name can be a pseudonym, it just helps us with the head count.",
    explainerEmailIntro:
      "Your email is optional. If you leave it, we store it encrypted and use it for:",
    explainerEmailOutro:
      "Once every email related to this event has been sent, we permanently delete your address.",
    explainerSource: "The full source code of this app is",
    explainerLink: "openly available",
    imageCredit: "Design:",
  },
};

export function pickLocale(eventLocale: string | undefined): Locale {
  // ``?lang=`` URL override beats the event's own locale; useful for
  // share-with-an-English-speaking-friend cases without touching the
  // organiser-side setting.
  const url = new URL(window.location.href);
  const override = url.searchParams.get("lang");
  if (override === "nl" || override === "en") return override;
  return eventLocale === "en" ? "en" : "nl";
}

export function strings(locale: Locale): Strings {
  return dict[locale];
}
