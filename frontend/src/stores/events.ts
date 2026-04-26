import { defineStore } from "pinia";
import { ref } from "vue";
import { get, post } from "@/api/client";

export interface EventOut {
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
  signup_count: number;
}

export interface EventStats {
  total_signups: number;
  total_attendees: number;
  by_source: Record<string, number>;
}

export interface EventCreate {
  name: string;
  topic: string | null;
  location: string;
  latitude: number | null;
  longitude: number | null;
  starts_at: string;
  ends_at: string;
  source_options: string[];
}

export const useEventsStore = defineStore("events", () => {
  const mine = ref<EventOut[]>([]);

  async function fetchMine(): Promise<void> {
    mine.value = await get<EventOut[]>("/api/v1/events/mine");
  }

  async function create(payload: EventCreate): Promise<EventOut> {
    const created = await post<EventOut>("/api/v1/events", payload);
    mine.value = [created, ...mine.value];
    return created;
  }

  async function getBySlug(slug: string): Promise<EventOut> {
    return get<EventOut>(`/api/v1/events/by-slug/${slug}`);
  }

  async function getStats(eventId: string): Promise<EventStats> {
    return get<EventStats>(`/api/v1/events/${eventId}/stats`);
  }

  async function signUp(slug: string, payload: {
    display_name: string;
    party_size: number;
    source_choice: string;
    email: string | null;
  }): Promise<void> {
    await post(`/api/v1/events/by-slug/${slug}/signups`, payload);
  }

  return { mine, fetchMine, create, getBySlug, getStats, signUp };
});
