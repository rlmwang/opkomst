/**
 * Wire types and calls for the quiz mini-app.
 *
 * The question shape is the questionnaire's, minus nothing: the server
 * sends the same ``PublicQuestionOut`` for both products, and it has no
 * answer key in it (``docs/design-quizzes.md`` part 3.2). The key
 * arrives once, in the result, after the answering is over.
 */

import type { PublicForm, PublicFormQuestion, SubmitAnswer } from "@/public_form/api";
import { ApiError } from "@/public_form/api";
import { inlinedSubmission } from "@/public_shared/submission";

export type { PublicForm as PublicQuiz, PublicFormQuestion as PublicQuizQuestion, SubmitAnswer };
export { ApiError };

export interface QuizAnswerResult {
  question_id: string;
  awarded: number;
  points: number;
  correct: boolean;
  /** What this person answered. Always sent: it is their own answer. */
  given_int: number | null;
  given_text: string | null;
  given_choices: string[] | null;
  /** Null when the organiser turned the reveal off. */
  correct_int: number | null;
  correct_text: string | null;
  correct_choices: string[] | null;
}

export interface QuizResult {
  submission_id: string;
  edit_token: string;
  score: number;
  max_score: number;
  reveal_answers: boolean;
  answers: QuizAnswerResult[];
}

export async function fetchQuizBySlug(slug: string): Promise<PublicForm> {
  const r = await fetch(`/api/v1/quiz/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicForm;
}

export async function postQuizAnswers(
  slug: string,
  payload: { display_name: string | null; answers: SubmitAnswer[] },
): Promise<QuizResult> {
  const r = await fetch(`/api/v1/quiz/by-slug/${encodeURIComponent(slug)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`submit failed (${r.status})`, r.status);
  return (await r.json()) as QuizResult;
}

/** The result again, later. Read-only: a quiz submission has no PUT,
 *  because changing an answer after seeing the score is a second
 *  attempt rather than a correction. */
export async function fetchQuizResult(token: string): Promise<QuizResult> {
  // The server already resolved this token when it built the page, so
  // in production there is nothing to ask for. The fetch below is the
  // dev server's path, where the shell's markers are left unfilled.
  const inlined = inlinedSubmission<QuizResult>();
  if (inlined !== undefined) {
    if (inlined === null) throw new ApiError("this link no longer opens anything", 410);
    return inlined;
  }
  const r = await fetch(`/api/v1/quiz/by-token/${encodeURIComponent(token)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as QuizResult;
}

declare global {
  interface Window {
    /** Server-side-injected quiz payload, same contract as
     *  ``__OPKOMST_FORM__``: ``null`` when the slug is unknown or the
     *  quiz is archived, ``undefined`` in dev without the backend. */
    __OPKOMST_QUIZ__?: PublicForm | null;
  }
}
