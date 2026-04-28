import { defineStore } from "pinia";
import { ref } from "vue";
import type {
  EventCreate,
  EventOut,
  EventStats,
  SignupSummary,
} from "@/api/types";
import { get, post, put } from "@/api/client";

export type { EventCreate, EventOut, EventStats, SignupSummary };

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

  async function sendEmailsNow(
    eventId: string,
    channel: "reminder" | "feedback",
  ): Promise<{ processed: number }> {
    return post<{ processed: number }>(
      `/api/v1/events/${eventId}/send-emails/${channel}`,
    );
  }

  async function getBySlug(slug: string): Promise<EventOut> {
    return get<EventOut>(`/api/v1/events/by-slug/${slug}`);
  }

  async function getStats(eventId: string): Promise<EventStats> {
    return get<EventStats>(`/api/v1/events/${eventId}/stats`);
  }

  async function getSignups(eventId: string): Promise<SignupSummary[]> {
    return get<SignupSummary[]>(`/api/v1/events/${eventId}/signups`);
  }

  async function signUp(slug: string, payload: {
    display_name: string | null;
    party_size: number;
    source_choice: string | null;
    help_choices: string[];
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
    sendEmailsNow,
    getBySlug,
    getStats,
    getSignups,
    signUp,
  };
});
