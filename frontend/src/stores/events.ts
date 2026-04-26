import { defineStore } from "pinia";
import { ref } from "vue";
import { get, post, put } from "@/api/client";

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
  questionnaire_enabled: boolean;
  afdeling_id: string | null;
  afdeling_name: string | null;
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
  questionnaire_enabled: boolean;
}

export const useEventsStore = defineStore("events", () => {
  const all = ref<EventOut[]>([]);
  const archived = ref<EventOut[]>([]);

  async function fetchAll(): Promise<void> {
    all.value = await get<EventOut[]>("/api/v1/events");
  }

  async function fetchArchived(): Promise<void> {
    archived.value = await get<EventOut[]>("/api/v1/events/archived");
  }

  async function create(payload: EventCreate): Promise<EventOut> {
    const created = await post<EventOut>("/api/v1/events", payload);
    all.value = [created, ...all.value];
    return created;
  }

  async function update(eventId: string, payload: EventCreate): Promise<EventOut> {
    const updated = await put<EventOut>(`/api/v1/events/${eventId}`, payload);
    all.value = all.value.map((e) => (e.id === eventId ? updated : e));
    return updated;
  }

  async function archive(eventId: string): Promise<void> {
    await post(`/api/v1/events/${eventId}/archive`);
    all.value = all.value.filter((e) => e.id !== eventId);
  }

  async function restore(eventId: string): Promise<void> {
    const restored = await post<EventOut>(`/api/v1/events/${eventId}/restore`);
    archived.value = archived.value.filter((e) => e.id !== eventId);
    all.value = [restored, ...all.value];
  }

  async function sendFeedbackEmailsNow(eventId: string): Promise<{ processed: number }> {
    return post<{ processed: number }>(`/api/v1/events/${eventId}/send-feedback-emails`);
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

  return {
    all,
    archived,
    fetchAll,
    fetchArchived,
    create,
    update,
    archive,
    restore,
    sendFeedbackEmailsNow,
    getBySlug,
    getStats,
    signUp,
  };
});
