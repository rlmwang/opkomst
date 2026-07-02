/**
 * Chore-specific strings for the public takenrooster mini-app. Shared
 * page chrome (loading / unavailable / submit / pseudonym / disclosure /
 * edit link) lives in ``@/public_shared/strings``; only the chore-
 * specific copy lives here.
 */

import type { Locale } from "@/public_shared/strings";

export interface ChoreStrings {
  enrolIntro: string;
  chooseChores: string;
  noChores: string;
  emailLabel: string;
  emailDisclosureBody: string;
  enrolButton: string;
  enrolled: string;
  saveChanges: string;
  saved: string;
  myTurns: string;
  noUpcoming: string;
  coveringForLeaver: string;
  upForGrabs: string;
  noOpen: string;
  markDone: string;
  cantMakeIt: string;
  claim: string;
  coverHeading: string;
  coverButton: string;
  coverForName: string;
  noCoverable: string;
  outlookHeading: string;
  outlookNote: string;
  noOutlook: string;
  availabilityHeading: string;
  availabilityHint: string;
  availabilityAdd: string;
  availabilityRemove: string;
  availabilitySave: string;
  availabilityFrom: string;
  availabilityTo: string;
  availabilityEmpty: string;
  leave: string;
  leaveConfirm: string;
  left: string;
  actionFailed: string;
  everyKWeeks: string;
  weekdays: [string, string, string, string, string, string, string];
}

const dict: Record<Locale, ChoreStrings> = {
  nl: {
    enrolIntro: "Kies de taken die je op je wilt nemen. Je wordt eerlijk ingedeeld.",
    chooseChores: "Taken",
    noChores: "Er zijn nog geen taken.",
    emailLabel: "E-mail (optioneel)",
    emailDisclosureBody:
      "Je e-mailadres gebruiken we alleen om je op tijd aan een taak te herinneren. We bewaren het versleuteld zolang je meedoet en verwijderen het zodra je je afmeldt.",
    enrolButton: "Aanmelden",
    enrolled: "Je bent aangemeld!",
    saveChanges: "Wijzigingen opslaan",
    saved: "Opgeslagen",
    myTurns: "Mijn taken",
    noUpcoming: "Je hebt geen komende taken.",
    coveringForLeaver: "Overgenomen voor iemand die vertrok",
    upForGrabs: "Vrije taken",
    noOpen: "Geen vrije taken om over te nemen.",
    markDone: "Gedaan",
    cantMakeIt: "Kan niet — vind iemand anders",
    claim: "Overnemen",
    coverHeading: "Voor iemand invallen",
    coverButton: "Invallen",
    coverForName: "Taak van {name}",
    noCoverable: "Geen taken om voor in te vallen.",
    outlookHeading: "Verwachte taken",
    outlookNote: "Voorlopig — dit kan nog veranderen.",
    noOutlook: "Nog geen verwachte taken.",
    availabilityHeading: "Afwezigheid",
    availabilityHint: "Geef periodes op waarin je niet kunt. Je wordt dan niet ingedeeld.",
    availabilityAdd: "Periode toevoegen",
    availabilityRemove: "Verwijderen",
    availabilitySave: "Afwezigheid opslaan",
    availabilityFrom: "Van",
    availabilityTo: "Tot en met",
    availabilityEmpty: "Je hebt geen afwezigheid opgegeven.",
    leave: "Afmelden",
    leaveConfirm: "Weet je zeker dat je je wilt afmelden? Je e-mailadres wordt verwijderd.",
    left: "Je bent afgemeld.",
    actionFailed: "Er ging iets mis. Probeer het opnieuw.",
    everyKWeeks: "Elke {k} weken",
    weekdays: ["ma", "di", "wo", "do", "vr", "za", "zo"],
  },
  en: {
    enrolIntro: "Pick the chores you'll take on. You'll be assigned fairly.",
    chooseChores: "Chores",
    noChores: "There are no chores yet.",
    emailLabel: "Email (optional)",
    emailDisclosureBody:
      "We only use your email to send you a reminder before your shift. It's stored encrypted while you're taking part and deleted as soon as you leave.",
    enrolButton: "Sign up",
    enrolled: "You're signed up!",
    saveChanges: "Save changes",
    saved: "Saved",
    myTurns: "My shifts",
    noUpcoming: "You have no upcoming shifts.",
    coveringForLeaver: "Picked up, covering for someone who left",
    upForGrabs: "Up for grabs",
    noOpen: "No open shifts to take on.",
    markDone: "Done",
    cantMakeIt: "Can't make it — find someone else",
    claim: "Take it on",
    coverHeading: "Cover for someone",
    coverButton: "Cover",
    coverForName: "{name}'s shift",
    noCoverable: "No shifts to cover right now.",
    outlookHeading: "Expected shifts",
    outlookNote: "Tentative — this may still change.",
    noOutlook: "No expected shifts yet.",
    availabilityHeading: "Time off",
    availabilityHint: "Add periods when you can't take part. You won't be scheduled then.",
    availabilityAdd: "Add a period",
    availabilityRemove: "Remove",
    availabilitySave: "Save time off",
    availabilityFrom: "From",
    availabilityTo: "Until (inclusive)",
    availabilityEmpty: "You haven't set any time off.",
    leave: "Leave",
    leaveConfirm: "Are you sure you want to leave? Your email will be deleted.",
    left: "You've left.",
    actionFailed: "Something went wrong. Please try again.",
    everyKWeeks: "Every {k} weeks",
    weekdays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  },
};

export function choreStrings(locale: Locale): ChoreStrings {
  return dict[locale];
}

/** Long human-readable date: ``Monday 27 April``. */
export function formatLongDate(iso: string, locale: Locale): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale === "en" ? "en-GB" : "nl-NL", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}
