/**
 * Bare-fetch API for the public sign-up mini-app. No Vue Query, no axios.
 *
 * The page loads by OCCURRENCE slug. Server injects the event content +
 * the occurrence context as ``window.__OPKOMST_EVENT__`` (PublicEvent);
 * the sign-up form can book several occurrences at once. A booking is
 * managed afterwards by its own edit-link token (``?s=…``), which lists
 * the occurrences the person is on, each individually withdrawable.
 */

import { inlinedSubmission } from "@/public_shared/submission";
/** A materialised, sign-up-able occurrence on the checklist.
 *  ``is_current`` marks the one whose page the visitor landed on. */
export interface PublicOccurrence {
  id: string;
  slug: string;
  index: number;
  starts_at: string;
  ends_at: string;
  is_current: boolean;
}

/** A beyond-horizon future date shown for context only: no row, no page
 *  yet, so not sign-up-able. */
export interface ProjectedOccurrence {
  index: number;
  starts_at: string;
  ends_at: string;
}

export interface PublicEvent {
  event_slug: string;
  name_nl: string | null;
  name_en: string | null;
  topic_nl: string | null;
  topic_en: string | null;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  source_options: string[];
  help_options: string[];
  image_url: string | null;
  image_artist_instagram: string | null;
  locale: string;
  archived: boolean;
  /** Which mails this event sends. The page asks for an address only
   *  when one of them will use it. */
  /** Whether the page insists on a (pseudo)name before it will accept
   *  anything, and whether a booking may still be changed through its
   *  own link. Both the organiser's. */
  name_required: boolean;
  answers_editable: boolean;
  reminder_enabled: boolean;
  feedback_enabled: boolean;
  is_recurring: boolean;
  total_sessions: number | null;
  current: PublicOccurrence;
  upcoming: PublicOccurrence[];
  projected: ProjectedOccurrence[];
}

export interface SignupPayload {
  display_name: string | null;
  party_size: number;
  source_choice: string | null;
  help_choices: string[];
  email: string | null;
  /** Explicit occurrence ids to book (ignored when ``all_upcoming``). */
  occurrence_ids: string[];
  /** Let the server resolve "every upcoming occurrence" so a stale page
   *  can't book a session already past. */
  all_upcoming: boolean;
}

export interface SignupAck {
  /** Secret edit-link token, returned once. Not recoverable later. */
  edit_token: string;
}

/** One occurrence a booking is on, as shown on the manage page.
 *  ``is_past`` sessions are frozen history: shown locked, never editable. */
export interface BookingOccurrence {
  occurrence_id: string;
  slug: string;
  index: number;
  starts_at: string;
  ends_at: string;
  is_past: boolean;
  source_choice: string | null;
  help_choices: string[];
}

/** The whole booking behind an edit-link token. */
export interface Booking {
  display_name: string | null;
  party_size: number;
  link_recovered_at?: string | null;
  event_name: string;
  event_slug: string;
  locale: string;
  occurrences: BookingOccurrence[];
}

/** The edit payload: name + party size only. Occurrence membership is
 *  changed by withdrawing sessions, not by editing this. */
export interface BookingEditPayload {
  display_name: string | null;
  party_size: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function fetchEventBySlug(slug: string): Promise<PublicEvent> {
  const r = await fetch(`/api/v1/event/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicEvent;
}

export async function postSignup(
  slug: string,
  payload: SignupPayload,
): Promise<SignupAck> {
  const r = await fetch(
    `/api/v1/event/by-slug/${encodeURIComponent(slug)}/signups`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!r.ok) throw new ApiError(`signup failed (${r.status})`, r.status);
  return (await r.json()) as SignupAck;
}

export async function fetchBooking(token: string): Promise<Booking> {
  // The server already resolved this token when it built the page, so
  // in production there is nothing to ask for. The fetch below is the
  // dev server's path, where the shell's markers are left unfilled.
  const inlined = inlinedSubmission<Booking>();
  if (inlined !== undefined) {
    if (inlined === null) throw new ApiError("this link no longer opens anything", 410);
    return inlined;
  }
  const r = await fetch(`/api/v1/event/by-token/${encodeURIComponent(token)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as Booking;
}

export async function putBooking(
  token: string,
  payload: BookingEditPayload,
): Promise<Booking> {
  const r = await fetch(`/api/v1/event/by-token/${encodeURIComponent(token)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`update failed (${r.status})`, r.status);
  return (await r.json()) as Booking;
}

/** Replace the booking's future session set (the manage-page calendar).
 *  Same target shape as sign-up; the server diffs it against the current
 *  future line items and never touches past (frozen) sessions. */
export async function putBookingOccurrences(
  token: string,
  payload: { occurrence_ids: string[]; all_upcoming: boolean },
): Promise<Booking> {
  const r = await fetch(
    `/api/v1/event/by-token/${encodeURIComponent(token)}/occurrences`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!r.ok) throw new ApiError(`update failed (${r.status})`, r.status);
  return (await r.json()) as Booking;
}

/** Withdraw the booking from one occurrence (per-occurrence absence). */
export async function withdrawOccurrence(
  token: string,
  occurrenceId: string,
): Promise<void> {
  const r = await fetch(
    `/api/v1/event/by-token/${encodeURIComponent(token)}/occurrences/${encodeURIComponent(occurrenceId)}/withdraw`,
    { method: "POST" },
  );
  if (!r.ok) throw new ApiError(`withdraw failed (${r.status})`, r.status);
}

/** Withdraw the whole booking (every occurrence at once). */
export async function withdrawBooking(token: string): Promise<void> {
  const r = await fetch(
    `/api/v1/event/by-token/${encodeURIComponent(token)}/withdraw`,
    { method: "POST" },
  );
  if (!r.ok) throw new ApiError(`withdraw failed (${r.status})`, r.status);
}

declare global {
  interface Window {
    /**
     * Server-side-injected event payload. Read at mount time so the form
     * has data without a network round-trip. ``null`` when the slug
     * isn't known (rendered 404 by the mini-app); ``undefined`` only in
     * dev when the SPA fallback isn't doing the inlining.
     */
    __OPKOMST_EVENT__?: PublicEvent | null;
  }
}

export {};
