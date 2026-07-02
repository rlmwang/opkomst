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
  emailReminders: string;
  emailDisclosureTitle: string;
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
  reminderState: string;
  leave: string;
  leaveConfirm: string;
  left: string;
  actionFailed: string;
  everyKWeeks: string;
  weekLabel: string;
  weekdays: [string, string, string, string, string, string, string];
}

const dict: Record<Locale, ChoreStrings> = {
  nl: {
    enrolIntro: "Kies de taken die je op je wilt nemen. Je wordt eerlijk ingedeeld.",
    chooseChores: "Taken",
    noChores: "Er zijn nog geen taken.",
    emailLabel: "E-mail (optioneel)",
    emailReminders: "Stuur me een herinnering voor mijn beurt",
    emailDisclosureTitle: "Wat gebeurt er met mijn e-mail?",
    emailDisclosureBody:
      "Als je herinneringen aanzet, bewaren we je e-mailadres versleuteld zolang je meedoet, alleen om je aan je beurt te herinneren. Meld je af of zet herinneringen uit en we verwijderen het meteen.",
    enrolButton: "Aanmelden",
    enrolled: "Je bent aangemeld!",
    saveChanges: "Wijzigingen opslaan",
    saved: "Opgeslagen",
    myTurns: "Mijn beurten",
    noUpcoming: "Je hebt geen komende beurten.",
    coveringForLeaver: "Overgenomen voor iemand die vertrok",
    upForGrabs: "Vrije beurten",
    noOpen: "Geen vrije beurten om over te nemen.",
    markDone: "Gedaan",
    cantMakeIt: "Kan niet — vind iemand anders",
    claim: "Overnemen",
    coverHeading: "Voor iemand invallen",
    coverButton: "Invallen",
    coverForName: "Beurt van {name}",
    noCoverable: "Geen beurten om voor in te vallen.",
    outlookHeading: "Verwachte beurten",
    outlookNote: "Voorlopig — dit kan nog veranderen.",
    noOutlook: "Nog geen verwachte beurten.",
    availabilityHeading: "Afwezigheid",
    availabilityHint: "Geef periodes op waarin je niet kunt. Je wordt dan niet ingedeeld.",
    availabilityAdd: "Periode toevoegen",
    availabilityRemove: "Verwijderen",
    availabilitySave: "Afwezigheid opslaan",
    availabilityFrom: "Van",
    availabilityTo: "Tot en met",
    availabilityEmpty: "Je hebt geen afwezigheid opgegeven.",
    reminderState: "E-mailherinneringen",
    leave: "Afmelden",
    leaveConfirm: "Weet je zeker dat je je wilt afmelden? Je e-mailadres wordt verwijderd.",
    left: "Je bent afgemeld.",
    actionFailed: "Er ging iets mis. Probeer het opnieuw.",
    everyKWeeks: "Elke {k} weken",
    weekLabel: "Week {n}",
    weekdays: ["ma", "di", "wo", "do", "vr", "za", "zo"],
  },
  en: {
    enrolIntro: "Pick the chores you'll take on. You'll be assigned fairly.",
    chooseChores: "Chores",
    noChores: "There are no chores yet.",
    emailLabel: "Email (optional)",
    emailReminders: "Remind me before my turn",
    emailDisclosureTitle: "What happens to my email?",
    emailDisclosureBody:
      "If you turn on reminders, we keep your email encrypted for as long as you're signed up, only to remind you of your turns. Leave or switch reminders off and we delete it on the spot.",
    enrolButton: "Sign up",
    enrolled: "You're signed up!",
    saveChanges: "Save changes",
    saved: "Saved",
    myTurns: "My turns",
    noUpcoming: "You have no upcoming turns.",
    coveringForLeaver: "Picked up, covering for someone who left",
    upForGrabs: "Up for grabs",
    noOpen: "No open turns to take on.",
    markDone: "Done",
    cantMakeIt: "Can't make it — find someone else",
    claim: "Take it on",
    coverHeading: "Cover for someone",
    coverButton: "Cover",
    coverForName: "{name}'s turn",
    noCoverable: "No turns to cover right now.",
    outlookHeading: "Expected turns",
    outlookNote: "Tentative — this may still change.",
    noOutlook: "No expected turns yet.",
    availabilityHeading: "Time off",
    availabilityHint: "Add periods when you can't take part. You won't be scheduled then.",
    availabilityAdd: "Add a period",
    availabilityRemove: "Remove",
    availabilitySave: "Save time off",
    availabilityFrom: "From",
    availabilityTo: "Until (inclusive)",
    availabilityEmpty: "You haven't set any time off.",
    reminderState: "Email reminders",
    leave: "Leave",
    leaveConfirm: "Are you sure you want to leave? Your email will be deleted.",
    left: "You've left.",
    actionFailed: "Something went wrong. Please try again.",
    everyKWeeks: "Every {k} weeks",
    weekLabel: "Week {n}",
    weekdays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  },
};

export function choreStrings(locale: Locale): ChoreStrings {
  return dict[locale];
}

/** Readable day summary for a chore's cycle_slots, grouped by week when
 *  the roster's cycle is longer than one week. */
export function formatCycle(cycleSlots: number[], periodWeeks: number, s: ChoreStrings): string {
  if (cycleSlots.length === 0) return "—";
  if (periodWeeks <= 1) {
    return cycleSlots.map((o) => s.weekdays[o % 7]).join(", ");
  }
  const parts: string[] = [];
  for (let w = 0; w < periodWeeks; w++) {
    const days = cycleSlots.filter((o) => Math.floor(o / 7) === w).map((o) => s.weekdays[o % 7]);
    if (days.length) parts.push(`${s.weekLabel.replace("{n}", String(w + 1))}: ${days.join(", ")}`);
  }
  return parts.join(" · ");
}

/** Long human-readable date: ``Monday 27 April``. */
export function formatLongDate(iso: string, locale: Locale): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale === "en" ? "en-GB" : "nl-NL", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}
