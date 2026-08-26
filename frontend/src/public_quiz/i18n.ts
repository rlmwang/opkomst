/**
 * Quiz-specific strings. The shared page chrome (loading, unavailable,
 * the pseudonym field, the disclosure) comes from
 * ``@/public_shared/strings``; only the words a questionnaire never
 * needs live here.
 */

import type { Locale } from "@/public_shared/strings";

export interface QuizStrings {
  required: string;
  /** What a number question will accept, in words: the bounds it sits
   *  between and how far off an answer may be. Null when it says
   *  neither, which is a box that takes any whole number. The unit is
   *  not repeated here, it is already beside the box. */
  range: (min: number | null, max: number | null, tolerance: number | null, step: number | null) => string | null;
  answerFirst: string;
  progress: (n: number, total: number) => string;
  back: string;
  next: string;
  finish: string;
  points: string;
  questionsRight: (right: number, total: number) => string;
  correct: string;
  wrong: string;
  yourAnswer: string;
  rightAnswer: string;
  missed: string;
  noAnswer: string;
  /** The cover: what this is, and the one thing it asks before the
   *  questions start. */
  coverName: string;
  start: string;
}

const dict: Record<Locale, QuizStrings> = {
  nl: {
    required: "verplicht",
    range: (min, max, tolerance, step) => {
      const named = step && step > 1 ? `stapgrootte ${step}` : null;
      const bounds =
        min !== null && max !== null
          ? `tussen ${min} en ${max}`
          : min !== null
            ? `${min} of meer`
            : max !== null
              ? `${max} of minder`
              : null;
      // A margin is worth saying: it is the rule the answer is marked
      // by, not the answer.
      const margin = tolerance ? `je mag er ${tolerance} naast zitten` : null;
      return [named, bounds, margin].filter(Boolean).join(", ") || null;
    },
    answerFirst: "Geef eerst een antwoord op deze vraag.",
    progress: (n, total) => `Vraag ${n} van ${total}`,
    back: "Vorige",
    next: "Volgende",
    finish: "Klaar",
    points: "punten",
    questionsRight: (right, total) => `${right} van de ${total} vragen goed`,
    correct: "goed",
    wrong: "fout",
    yourAnswer: "jouw antwoord",
    rightAnswer: "goed antwoord",
    missed: "gemist",
    noAnswer: "niets ingevuld",
    coverName: "Je naam, zodat de organisator weet wie welke score haalde. Een schuilnaam mag, of laat het leeg.",
    start: "Beginnen",
  },
  en: {
    required: "required",
    range: (min, max, tolerance, step) => {
      const named = step && step > 1 ? `step size ${step}` : null;
      const bounds =
        min !== null && max !== null
          ? `between ${min} and ${max}`
          : min !== null
            ? `${min} or more`
            : max !== null
              ? `${max} or less`
              : null;
      const margin = tolerance ? `you can be ${tolerance} off` : null;
      return [named, bounds, margin].filter(Boolean).join(", ") || null;
    },
    answerFirst: "Answer this question first.",
    progress: (n, total) => `Question ${n} of ${total}`,
    back: "Back",
    next: "Next",
    finish: "Finish",
    points: "points",
    questionsRight: (right, total) => `${right} of ${total} questions right`,
    correct: "right",
    wrong: "wrong",
    yourAnswer: "your answer",
    rightAnswer: "right answer",
    missed: "missed",
    noAnswer: "left empty",
    coverName: "Your name, so the organiser knows who got which score. A pseudonym is fine, or leave it empty.",
    start: "Start",
  },
};

export function quizStrings(locale: Locale): QuizStrings {
  return dict[locale];
}
