/**
 * Wire types and calls for the kompas mini-app.
 *
 * The question shape is the questionnaire's, minus the directions: the
 * server sends the same ``PublicQuestionOut`` for all three products
 * and it carries neither ``pole`` nor ``option_poles``
 * (``docs/design-kompas.md`` 5.2). They arrive once, with the result,
 * after the answering is over: a page that says which button moves you
 * where is a page people answer to land somewhere.
 */

import type { PublicAxis, PublicForm, PublicFormQuestion, SubmitAnswer } from "@/public_form/api";
import { ApiError } from "@/public_form/api";
import { inlinedSubmission } from "@/public_shared/submission";

export type {
  PublicForm as PublicCompass,
  PublicFormQuestion as PublicCompassQuestion,
  PublicAxis as CompassAxis,
  SubmitAnswer,
};
export { ApiError };

export type Pole = "x_low" | "x_high" | "y_low" | "y_high";

/** One axis with where the whole room sits on it. ``ci_low`` /
 *  ``ci_high`` are the ends of the 95% confidence interval around the
 *  mean, so a room that agrees draws a narrow band and a room that is
 *  split draws a wide one. All three are null before anybody has
 *  filled it in. */
export interface CompassAxisRoom {
  axis: PublicAxis;
  average: number | null;
  ci_low: number | null;
  ci_high: number | null;
}

export interface CompassPoint {
  name: string | null;
  x: number;
  y: number;
  you: boolean;
}

export interface CompassAnswerResult {
  question_id: string;
  kind: string;
  /** A rating's own direction: the side a 5 meant. */
  pole: Pole | null;
  /** A choice's, one per option in the options' own order. */
  option_poles: Pole[] | null;
  given_int: number | null;
  given_choices: string[] | null;
  /** What this answer was worth, on the axis it spoke to. Null when it
   *  said nothing: skipped, or a question with no direction on it. */
  axis: string | null;
  value: number | null;
}

export interface CompassResult {
  submission_id: string;
  edit_token: string;
  display_name: string | null;
  link_recovered_at: string | null;
  x: number;
  y: number;
  /** How many answers spoke to each axis. Zero is the difference
   *  between "your answers balanced" and "you said nothing about
   *  this", and the screen says which. */
  counted_x: number;
  counted_y: number;
  axes: CompassAxisRoom[];
  answers: CompassAnswerResult[];
  points: CompassPoint[];
}

export async function fetchCompassBySlug(slug: string): Promise<PublicForm> {
  const r = await fetch(`/api/v1/compass/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicForm;
}

export async function postCompassAnswers(
  slug: string,
  payload: { display_name: string | null; answers: SubmitAnswer[] },
): Promise<CompassResult> {
  const r = await fetch(`/api/v1/compass/by-slug/${encodeURIComponent(slug)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`submit failed (${r.status})`, r.status);
  return (await r.json()) as CompassResult;
}

/** The map again, later, redrawn against the room as it stands. The
 *  per-answer rows carry what was given, so this one call both renders
 *  the result and refills the walk behind "change your answers". */
export async function fetchCompassResult(token: string): Promise<CompassResult> {
  // The server already resolved this token when it built the page, so
  // in production there is nothing to ask for. The fetch below is the
  // dev server's path, where the shell's markers are left unfilled.
  const inlined = inlinedSubmission<CompassResult>();
  if (inlined !== undefined) {
    if (inlined === null) throw new ApiError("this link no longer opens anything", 410);
    return inlined;
  }
  const r = await fetch(`/api/v1/compass/by-token/${encodeURIComponent(token)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as CompassResult;
}

/** Change your mind. Unlike a quiz this is a correction rather than a
 *  second attempt: a kompas has nothing to score and nothing to beat. */
export async function putCompassAnswers(
  token: string,
  payload: { display_name: string | null; answers: SubmitAnswer[] },
): Promise<CompassResult> {
  const r = await fetch(`/api/v1/compass/by-token/${encodeURIComponent(token)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`update failed (${r.status})`, r.status);
  return (await r.json()) as CompassResult;
}

export async function withdrawCompass(token: string): Promise<void> {
  const r = await fetch(`/api/v1/compass/by-token/${encodeURIComponent(token)}/withdraw`, { method: "POST" });
  if (!r.ok) throw new ApiError(`withdraw failed (${r.status})`, r.status);
}

declare global {
  interface Window {
    /** Server-side-injected kompas payload, same contract as
     *  ``__OPKOMST_FORM__``: ``null`` when the slug is unknown or the
     *  kompas is archived, ``undefined`` in dev without the backend. */
    __OPKOMST_COMPASS__?: PublicForm | null;
  }
}
