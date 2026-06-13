/**
 * Bare-fetch API for the public datepoll mini-app. No Vue Query, no
 * axios — one POST (submit) and (rarely) one GET fallback when the
 * server-side inlining is missing (dev without the backend fronting
 * Vite). Mirrors ``src/public_form/api.ts``.
 */

export type Availability = "yes" | "no" | "maybe";

export interface PublicDatepollDate {
  id: string;
  on_date: string; // YYYY-MM-DD
}

export interface PublicDatepoll {
  id: string;
  name: string;
  description: string | null;
  locale: "nl" | "en";
  dates: PublicDatepollDate[];
}

export interface SubmitAnswer {
  datepoll_date_id: string;
  availability: Availability;
  comment?: string | null;
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

export async function fetchDatepollBySlug(slug: string): Promise<PublicDatepoll> {
  const r = await fetch(`/api/v1/datepolls/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicDatepoll;
}

export async function postSubmission(slug: string, payload: SubmitPayload): Promise<void> {
  const r = await fetch(`/api/v1/datepolls/by-slug/${encodeURIComponent(slug)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`submit failed (${r.status})`, r.status);
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
