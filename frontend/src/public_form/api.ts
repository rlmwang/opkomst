/**
 * Bare-fetch API for the public form mini-app. No Vue Query, no
 * axios — the page makes one POST (submit) and (rarely) one GET
 * fallback for the form data when the server-side inlining is
 * missing (dev workflow without the backend in front of Vite).
 */

export interface PublicFormQuestion {
  id: string;
  ordinal: number;
  kind: "rating" | "text" | "short_text" | "single_choice" | "multi_choice";
  prompt: string;
  required: boolean;
  options: string[];
  low_label: string | null;
  high_label: string | null;
}

export interface PublicForm {
  id: string;
  name: string;
  description: string | null;
  image_url: string | null;
  image_artist_instagram: string | null;
  locale: "nl" | "en";
  questions: PublicFormQuestion[];
}

export interface SubmitAnswer {
  question_id: string;
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
}

export interface SubmitPayload {
  display_name?: string | null;
  answers: SubmitAnswer[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function fetchFormBySlug(slug: string): Promise<PublicForm> {
  const r = await fetch(`/api/v1/forms/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicForm;
}

export async function postSubmission(
  slug: string,
  payload: SubmitPayload,
): Promise<void> {
  const r = await fetch(
    `/api/v1/forms/by-slug/${encodeURIComponent(slug)}/submit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!r.ok) throw new ApiError(`submit failed (${r.status})`, r.status);
}

declare global {
  interface Window {
    /**
     * Server-side-injected form payload. Read at mount time so
     * the page has data without a network round-trip. ``null``
     * when the slug isn't known or the form is archived (the
     * mini-app renders a polite "no longer available" page);
     * ``undefined`` only in dev when the SPA fallback isn't
     * doing the inlining (mini-app falls back to a fetch).
     */
    __OPKOMST_FORM__?: PublicForm | null;
  }
}

export {};
