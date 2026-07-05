/**
 * Bare-fetch API for the public chore ("takenrooster") mini-app. No Vue
 * Query, no PrimeVue — same wire-weight target as the other public
 * mini-apps (``src/public_datepoll/api.ts``). One enrol POST, the
 * by-token personal-page GET/PUT, the three shift actions, and leave.
 */

import type { Locale } from "@/public_shared/strings";

export interface PublicChore {
  id: string;
  name: string;
  description: string | null;
  cycle_slots: number[];
  people_per_shift: number;
  emoji: string | null;
}

export interface PublicRoster {
  id: string;
  name: string;
  description: string | null;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  image_url: string | null;
  image_artist_instagram: string | null;
  locale: Locale;
  period_weeks: number;
  starts_on: string;
  ends_on: string | null;
  chores: PublicChore[];
}

export interface PersonalShift {
  id: string;
  chore_id: string;
  chore_name: string;
  on_date: string; // YYYY-MM-DD
  status: string;
  inherited: boolean; // picked up covering for someone who left
}

export interface PersonalOutlook {
  chore_id: string;
  chore_name: string;
  on_date: string;
}

export interface CoverableShift {
  id: string;
  chore_id: string;
  chore_name: string;
  on_date: string;
  assignee_name: string | null;
}

export interface AvailabilityRange {
  start: string; // YYYY-MM-DD
  end: string;
}

// The whole-roster calendar (organiser shape), for the "pitch in" overview.
export interface CalendarAssignee {
  name: string | null; // pseudonym; null = open slot
  open: boolean;
  status: string; // scheduled | done | missed
  shift_id: string | null; // null for a projected (tentative) day
}
export interface CalendarDay {
  on_date: string; // YYYY-MM-DD
  tentative: boolean; // beyond the commit horizon
  assignees: CalendarAssignee[];
}
export interface ChoreCalendar {
  chore_id: string;
  chore_name: string;
  emoji: string | null;
  days: CalendarDay[];
}

export interface PersonalPage {
  display_name: string | null;
  enrolled_chore_ids: string[];
  email_reminders: boolean;
  has_email: boolean;
  /** Non-null = an organiser recovered this volunteer's edit link. */
  link_recovered_at?: string | null;
  my_shifts: PersonalShift[];
  open_shifts: PersonalShift[];
  outlook_shifts?: PersonalOutlook[];
  coverable_shifts?: CoverableShift[];
  availability?: AvailabilityRange[];
}

export interface EnrollPayload {
  display_name?: string | null;
  email?: string | null;
  email_reminders: boolean;
  chore_ids: string[];
}

export interface EnrollEditPayload {
  display_name?: string | null;
  chore_ids: string[];
  email_reminders: boolean;
  email?: string | null;
}

export interface EnrollAck {
  edit_token: string;
}

export type ShiftAction = "done" | "pass" | "cover" | "claim";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

const JSON_HEADERS = { "Content-Type": "application/json" };

async function readJson<T>(r: Response, what: string): Promise<T> {
  if (!r.ok) throw new ApiError(`${what} failed (${r.status})`, r.status);
  return (await r.json()) as T;
}

export async function fetchRosterBySlug(slug: string): Promise<PublicRoster> {
  return readJson(await fetch(`/api/v1/chores/by-slug/${encodeURIComponent(slug)}`), "fetch");
}

export async function postEnrolment(slug: string, payload: EnrollPayload): Promise<EnrollAck> {
  const r = await fetch(`/api/v1/chores/by-slug/${encodeURIComponent(slug)}/enroll`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  return readJson(r, "enrol");
}

export async function fetchPersonalPage(token: string): Promise<PersonalPage> {
  return readJson(await fetch(`/api/v1/chores/by-token/${encodeURIComponent(token)}`), "fetch");
}

export async function fetchTokenCalendar(token: string, month: string): Promise<ChoreCalendar[]> {
  const url = `/api/v1/chores/by-token/${encodeURIComponent(token)}/calendar?month=${encodeURIComponent(month)}`;
  return readJson(await fetch(url), "fetch");
}

export async function putEnrolment(token: string, payload: EnrollEditPayload): Promise<PersonalPage> {
  const r = await fetch(`/api/v1/chores/by-token/${encodeURIComponent(token)}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  return readJson(r, "update");
}

export async function postShiftAction(token: string, shiftId: string, action: ShiftAction): Promise<PersonalPage> {
  const r = await fetch(
    `/api/v1/chores/by-token/${encodeURIComponent(token)}/shifts/${encodeURIComponent(shiftId)}/${action}`,
    { method: "POST" },
  );
  return readJson(r, action);
}

export async function postSwap(token: string, mineShiftId: string, theirsShiftId: string): Promise<PersonalPage> {
  const r = await fetch(`/api/v1/chores/by-token/${encodeURIComponent(token)}/swap`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ mine_shift_id: mineShiftId, theirs_shift_id: theirsShiftId }),
  });
  return readJson(r, "swap");
}

export async function putAvailability(token: string, ranges: AvailabilityRange[]): Promise<PersonalPage> {
  const r = await fetch(`/api/v1/chores/by-token/${encodeURIComponent(token)}/availability`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ ranges }),
  });
  return readJson(r, "availability");
}

export async function postLeave(token: string): Promise<void> {
  const r = await fetch(`/api/v1/chores/by-token/${encodeURIComponent(token)}/leave`, { method: "POST" });
  if (!r.ok) throw new ApiError(`leave failed (${r.status})`, r.status);
}

declare global {
  interface Window {
    /** Server-inlined roster payload; ``null`` when the slug is
     * unknown or the roster is archived; ``undefined`` only in dev
     * without the backend fronting Vite. */
    __OPKOMST_CHORE__?: PublicRoster | null;
  }
}

export {};
