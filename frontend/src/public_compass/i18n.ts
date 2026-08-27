/**
 * Kompas-specific strings. The shared page chrome (loading,
 * unavailable, the pseudonym field, the disclosure, the edit bar)
 * comes from ``@/public_shared/strings``; only the words the other two
 * products never need live here.
 */

import type { Locale } from "@/public_shared/strings";

export interface CompassStrings {
  required: string;
  answerFirst: string;
  progress: (n: number, total: number) => string;
  back: string;
  next: string;
  finish: string;
  /** The cover, and the sentence that is the privacy contract of this
   *  feature: the name is going on a chart other people read, said
   *  above the box rather than under it. */
  coverName: string;
  nameOnMap: string;
  start: string;
  /** The result. */
  resultTitle: string;
  anonymous: string;
  filledIn: (n: number) => string;
  /** Where you landed on one axis, in the organiser's own words. A dot
   *  on the centre line has two possible reasons and the screen says
   *  which one this is. */
  youAreAt: (pole: string) => string;
  youAreCentre: string;
  youSaidNothing: string;
  /** What the grey band behind your marker is. */
  roomBand: string;
  answersHeading: string;
  yourAnswer: string;
  noAnswer: string;
  /** What one rating answer did to the map, spelled out: "een 5 was
   *  Links, jij zei 4, dat is 0,5 richting Links". */
  ratingLine: (pole: string, given: number, value: string, toward: string) => string;
  ratingLineCentre: (pole: string, given: number) => string;
  changeAnswers: string;
}

/** The decimals a Dutch reader expects. The value is a small number
 *  between -1 and 1, so two places is the whole of it. */
function decimal(value: number, locale: Locale): string {
  const text = Math.abs(value).toFixed(2).replace(/0$/, "").replace(/\.$/, "");
  return locale === "nl" ? text.replace(".", ",") : text;
}

const dict: Record<Locale, CompassStrings> = {
  nl: {
    required: "verplicht",
    answerFirst: "Geef eerst een antwoord op deze vraag.",
    progress: (n, total) => `Vraag ${n} van ${total}`,
    back: "Vorige",
    next: "Volgende",
    finish: "Klaar",
    coverName: "Je naam. Een schuilnaam mag.",
    nameOnMap:
      "Je naam komt op de kaart. Die ziet iedereen die dit kompas invult. Laat 'm leeg als je liever anoniem meedoet.",
    start: "Beginnen",
    resultTitle: "Waar je staat",
    anonymous: "Anoniem",
    filledIn: (n) => (n === 1 ? "1 persoon vulde dit kompas in" : `${n} mensen vulden dit kompas in`),
    youAreAt: (pole) => `Je staat aan de kant van ${pole}.`,
    youAreCentre: "Je staat in het midden.",
    youSaidNothing: "Over deze as heb je niks ingevuld.",
    roomBand: "De grijze balk is waar de groep staat, met 95% zekerheid.",
    answersHeading: "Je antwoorden",
    yourAnswer: "jouw antwoord",
    noAnswer: "niets ingevuld",
    ratingLine: (pole, given, value, toward) =>
      `Een 5 was ${pole}, jij zei ${given}, dat is ${value} richting ${toward}.`,
    ratingLineCentre: (pole, given) => `Een 5 was ${pole}, jij zei ${given}, precies het midden.`,
    changeAnswers: "Verander je antwoorden",
  },
  en: {
    required: "required",
    answerFirst: "Answer this question first.",
    progress: (n, total) => `Question ${n} of ${total}`,
    back: "Back",
    next: "Next",
    finish: "Finish",
    coverName: "Your name. A pseudonym is fine.",
    nameOnMap:
      "Your name goes on the map everyone who fills this in can see. Leave it empty to take part anonymously.",
    start: "Start",
    resultTitle: "Where you stand",
    anonymous: "Anonymous",
    filledIn: (n) => (n === 1 ? "1 person filled in this compass" : `${n} people filled in this compass`),
    youAreAt: (pole) => `You are on the ${pole} side.`,
    youAreCentre: "You are in the middle.",
    youSaidNothing: "You did not answer any question on this axis.",
    roomBand: "The grey band is where the group sits, with 95% confidence.",
    answersHeading: "Your answers",
    yourAnswer: "your answer",
    noAnswer: "left empty",
    ratingLine: (pole, given, value, toward) =>
      `A 5 was ${pole}, you said ${given}, which is ${value} toward ${toward}.`,
    ratingLineCentre: (pole, given) => `A 5 was ${pole}, you said ${given}, exactly the middle.`,
    changeAnswers: "Change your answers",
  },
};

export function compassStrings(locale: Locale): CompassStrings {
  return dict[locale];
}

export { decimal };
