/**
 * Bare-fetch API for the public datepoll mini-app. No Vue Query, no
 * axios — one POST (submit) and (rarely) one GET fallback when the
 * server-side inlining is missing (dev without the backend fronting
 * Vite). Mirrors ``src/public_form/api.ts``.
 */

import { inlinedSubmission } from "@/public_shared/submission";
export type Availability = "yes" | "no" | "maybe";

export interface PublicDatepollSlot {
  id: string;
  on_date: string; // YYYY-MM-DD
  // Whole-day slot ⇒ both null; timed slot ⇒ both "HH:MM[:SS]".
  start_time: string | null;
  end_time: string | null;
}

export interface PublicDatepoll {
  /** Whether the page insists on a (pseudo)name before it will accept
   *  anything, and whether an answer may still be changed through its
   *  own link. Both the organiser's. */
  name_required: boolean;
  answers_editable: boolean;
  id: string;
  name_nl: string | null;
  name_en: string | null;
  description_nl: string | null;
  description_en: string | null;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  image_url: string | null;
  image_artist_instagram: string | null;
  locale: "nl" | "en";
  slots: PublicDatepollSlot[];
}

export interface SubmitAnswer {
  datepoll_slot_id: string;
  availability: Availability;
}

export interface SubmitPayload {
  display_name?: string | null;
  note?: string | null;
  answers: SubmitAnswer[];
}

export interface SubmitAck {
  /** Secret edit-link token, returned once. Not recoverable later. */
  edit_token: string;
}

/** A submission's current values for pre-filling the edit form:
 *  availability keyed by slot id, plus the whole-submission note. */
export interface DatepollSubmissionValues {
  display_name: string | null;
  note: string | null;
  answers: Record<string, Availability>;
  /** Non-null = an organiser recovered this submission's edit link. */
  link_recovered_at?: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function fetchDatepollBySlug(slug: string): Promise<PublicDatepoll> {
  const r = await fetch(`/api/v1/datepoll/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicDatepoll;
}

export async function postSubmission(slug: string, payload: SubmitPayload): Promise<SubmitAck> {
  const r = await fetch(`/api/v1/datepoll/by-slug/${encodeURIComponent(slug)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`submit failed (${r.status})`, r.status);
  return (await r.json()) as SubmitAck;
}

export async function fetchSubmission(token: string): Promise<DatepollSubmissionValues> {
  // The server already resolved this token when it built the page, so
  // in production there is nothing to ask for. The fetch below is the
  // dev server's path, where the shell's markers are left unfilled.
  const inlined = inlinedSubmission<DatepollSubmissionValues>();
  if (inlined !== undefined) {
    if (inlined === null) throw new ApiError("this link no longer opens anything", 410);
    return inlined;
  }
  const r = await fetch(`/api/v1/datepoll/by-token/${encodeURIComponent(token)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as DatepollSubmissionValues;
}

export async function putSubmission(token: string, payload: SubmitPayload): Promise<DatepollSubmissionValues> {
  const r = await fetch(`/api/v1/datepoll/by-token/${encodeURIComponent(token)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`update failed (${r.status})`, r.status);
  return (await r.json()) as DatepollSubmissionValues;
}

export async function withdrawSubmission(token: string): Promise<void> {
  const r = await fetch(`/api/v1/datepoll/by-token/${encodeURIComponent(token)}/withdraw`, { method: "POST" });
  if (!r.ok) throw new ApiError(`withdraw failed (${r.status})`, r.status);
}

declare global {
  interface Window {
    /**
     * Server-side-injected datepoll payload. Read at mount so the
     * page has data without a network round-trip. ``null`` when the
     * slug isn't known or the poll is archived; ``undefined`` only in
     * dev when the SPA fallback isn't doing the inlining.
     */
    __OPKOMST_DATEPOLL__?: PublicDatepoll | null;
  }
}

export {};
