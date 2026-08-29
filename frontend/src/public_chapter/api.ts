// Hand-written types + fetch for the chapter-agenda mini-app. Mirrors
// the backend ``ChapterAgendaOut`` / ``EventCardOut`` shapes. Kept off
// the generated schema.ts to keep the public bundle lean (same choice as
// the other public mini-apps).

// One agenda card is a single OCCURRENCE (``slug`` is the occurrence
// slug, linked as ``/e/{slug}``). ``index`` + ``total_sessions`` drive
// the "sessie i van N" badge (``total_sessions`` null = open-ended).
export interface EventCard {
  slug: string;
  name_nl: string | null;
  name_en: string | null;
  topic_nl: string | null;
  topic_en: string | null;
  starts_at: string;
  ends_at: string;
  location: string | null;
  image_url: string | null;
  image_artist_instagram: string | null;
  attendee_count: number;
  index: number;
  total_sessions: number | null;
}

export interface ChapterPublic {
  name: string;
  slug: string;
  city: string | null;
}

export interface ChapterAgenda {
  chapter: ChapterPublic;
  upcoming: EventCard[];
  past: EventCard[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Dev-only fallback: in ``vite dev`` the HTML has no server-injected
// payload (``window.__OPKOMST_CHAPTER__ === undefined``), so fetch the
// agenda over the ``/api`` proxy. In production the payload is inlined.
// The organisation is part of the path now, so it is part of the
// request: chapter slugs are unique within one, not across all.
export async function fetchChapterAgenda(tenant: string, slug: string): Promise<ChapterAgenda> {
  const r = await fetch(`/api/v1/tenants/${encodeURIComponent(tenant)}/agenda/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new ApiError(`fetch failed (${r.status})`, r.status);
  return r.json();
}

declare global {
  interface Window {
    __OPKOMST_CHAPTER__?: ChapterAgenda | null;
  }
}
