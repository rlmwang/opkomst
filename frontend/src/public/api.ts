/**
 * Bare-fetch API for the public mini-app. No Vue Query, no axios
 * — the page makes one POST (signup) and (rarely) one GET fallback
 * for the event data when the server-side inlining is missing.
 */

export interface PublicEvent {
  id: string;
  slug: string;
  name: string;
  topic: string | null;
  location: string;
  latitude: number | null;
  longitude: number | null;
  starts_at: string;
  ends_at: string;
  source_options: string[];
  help_options: string[];
  feedback_enabled: boolean;
  reminder_enabled: boolean;
  locale: string;
  archived: boolean;
  image_url: string | null;
  image_artist_instagram: string | null;
}

export interface SignupPayload {
  display_name: string | null;
  party_size: number;
  source_choice: string | null;
  help_choices: string[];
  email: string | null;
}

export interface SignupAck {
  /** Secret edit-link token, returned once. Not recoverable later. */
  edit_token: string;
}

/** A signup's current editable values, for pre-filling the edit form.
 *  Email is never returned — it isn't reachable from a signup. */
export interface SignupValues {
  display_name: string | null;
  party_size: number;
  source_choice: string | null;
  help_choices: string[];
}

/** The edit payload omits email: the address lives on decoupled
 *  dispatch rows with no link back to the signup, so it can't be
 *  changed here. */
export interface SignupEditPayload {
  display_name: string | null;
  party_size: number;
  source_choice: string | null;
  help_choices: string[];
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
  const r = await fetch(`/api/v1/events/by-slug/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as PublicEvent;
}

export async function postSignup(
  slug: string,
  payload: SignupPayload,
): Promise<SignupAck> {
  const r = await fetch(
    `/api/v1/events/by-slug/${encodeURIComponent(slug)}/signups`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!r.ok) throw new ApiError(`signup failed (${r.status})`, r.status);
  return (await r.json()) as SignupAck;
}

export async function fetchSignup(token: string): Promise<SignupValues> {
  const r = await fetch(`/api/v1/events/by-token/${encodeURIComponent(token)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return (await r.json()) as SignupValues;
}

export async function putSignup(
  token: string,
  payload: SignupEditPayload,
): Promise<SignupValues> {
  const r = await fetch(`/api/v1/events/by-token/${encodeURIComponent(token)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new ApiError(`update failed (${r.status})`, r.status);
  return (await r.json()) as SignupValues;
}

declare global {
  interface Window {
    /**
     * Server-side-injected event payload. Read at mount time so
     * the form has data without a network round-trip. ``null``
     * when the slug isn't known (rendered 404 by the mini-app);
     * ``undefined`` only in dev when the SPA fallback isn't
     * doing the inlining (mini-app falls back to a fetch).
     */
    __OPKOMST_EVENT__?: PublicEvent | null;
  }
}

export {};
