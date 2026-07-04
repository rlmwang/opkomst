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
  emailHidden: string;
  emailClearing: string;
  emailClear: string;
  emailKeep: string;
  emailDisclosureBody: string;
  enrolButton: string;
  enrolled: string;
  myTurns: string;
  noUpcoming: string;
  coveringForLeaver: string;
  helpOutHeading: string;
  markDone: string;
  cantMakeIt: string;
  claim: string;
  coverButton: string;
  prevMonth: string;
  nextMonth: string;
  calLocked: string;
  calTentative: string;
  calOpen: string;
  someone: string;
  availabilityHeading: string;
  availabilityHint: string;
  availabilityAdd: string;
  availabilityRemove: string;
  availabilityFrom: string;
  availabilityTo: string;
  availabilityEmpty: string;
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
    emailHidden: "E-mail (verborgen)",
    emailClearing: "E-mail (wordt verwijderd)",
    emailClear: "E-mail verwijderen",
    emailKeep: "E-mail behouden",
    emailDisclosureBody:
      "Je e-mailadres gebruiken we alleen om je op tijd aan een taak te herinneren. We bewaren het versleuteld zolang je meedoet en verwijderen het zodra je je afmeldt.",
    enrolButton: "Aanmelden",
    enrolled: "Je bent aangemeld!",
    myTurns: "Mijn taken",
    noUpcoming: "Je hebt geen komende taken.",
    coveringForLeaver: "Overgenomen voor iemand die vertrok",
    helpOutHeading: "Bijspringen",
    markDone: "Gedaan",
    cantMakeIt: "Kan niet — vind iemand anders",
    claim: "Overnemen",
    coverButton: "Invallen",
    prevMonth: "Vorige maand",
    nextMonth: "Volgende maand",
    calLocked: "Vast",
    calTentative: "Voorlopig",
    calOpen: "Vrij",
    someone: "Iemand",
    availabilityHeading: "Afwezigheid",
    availabilityHint: "Geef periodes op waarin je niet kunt. Je wordt dan niet ingedeeld.",
    availabilityAdd: "Periode toevoegen",
    availabilityRemove: "Verwijderen",
    availabilityFrom: "Startdatum",
    availabilityTo: "Einddatum",
    availabilityEmpty: "Je hebt geen afwezigheid opgegeven.",
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
    emailHidden: "Email (hidden)",
    emailClearing: "Email (will be removed)",
    emailClear: "Remove email",
    emailKeep: "Keep email",
    emailDisclosureBody:
      "We only use your email to send you a reminder before your shift. It's stored encrypted while you're taking part and deleted as soon as you leave.",
    enrolButton: "Sign up",
    enrolled: "You're signed up!",
    myTurns: "My shifts",
    noUpcoming: "You have no upcoming shifts.",
    coveringForLeaver: "Picked up, covering for someone who left",
    helpOutHeading: "Pitch in",
    markDone: "Done",
    cantMakeIt: "Can't make it — find someone else",
    claim: "Take it on",
    coverButton: "Cover",
    prevMonth: "Previous month",
    nextMonth: "Next month",
    calLocked: "Locked in",
    calTentative: "Tentative",
    calOpen: "Open",
    someone: "Someone",
    availabilityHeading: "Time off",
    availabilityHint: "Add periods when you can't take part. You won't be scheduled then.",
    availabilityAdd: "Add a period",
    availabilityRemove: "Remove",
    availabilityFrom: "Start date",
    availabilityTo: "End date",
    availabilityEmpty: "You haven't set any time off.",
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
