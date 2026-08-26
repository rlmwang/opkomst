/**
 * Quiz-specific strings. The shared page chrome (loading, unavailable,
 * the pseudonym field, the disclosure) comes from
 * ``@/public_shared/strings``; only the words a questionnaire never
 * needs live here.
 */

import type { Locale } from "@/public_shared/strings";

export interface QuizStrings {
  required: string;
  answerFirst: string;
  progress: (n: number, total: number) => string;
  back: string;
  next: string;
  finish: string;
  scoreHeading: string;
  scoreLine: (score: number, max: number) => string;
  correct: string;
  wrong: string;
  rightAnswer: string;
  yourAnswers: string;
  unscored: string;
}

const dict: Record<Locale, QuizStrings> = {
  nl: {
    required: "verplicht",
    answerFirst: "Geef eerst een antwoord op deze vraag.",
    progress: (n, total) => `Vraag ${n} van ${total}`,
    back: "Vorige",
    next: "Volgende",
    finish: "Klaar",
    scoreHeading: "Je score",
    scoreLine: (score, max) => `${score} van de ${max} punten`,
    correct: "Goed",
    wrong: "Fout",
    rightAnswer: "Goede antwoord:",
    yourAnswers: "Je antwoorden",
    unscored: "Telt niet mee",
  },
  en: {
    required: "required",
    answerFirst: "Answer this question first.",
    progress: (n, total) => `Question ${n} of ${total}`,
    back: "Back",
    next: "Next",
    finish: "Finish",
    scoreHeading: "Your score",
    scoreLine: (score, max) => `${score} out of ${max} points`,
    correct: "Right",
    wrong: "Wrong",
    rightAnswer: "Right answer:",
    yourAnswers: "Your answers",
    unscored: "Not scored",
  },
};

export function quizStrings(locale: Locale): QuizStrings {
  return dict[locale];
}
