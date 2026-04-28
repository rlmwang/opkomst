/**
 * Event composables.
 *
 * Replaces ``stores/events.ts``. Reads (list, archived list,
 * by-slug, stats, signups) are queries; writes (create, update,
 * archive, restore, send-emails-now, public signup) are mutations
 * that invalidate the affected lists.
 *
 * The ``signUp`` public mutation talks to a slug-keyed endpoint
 * but no list cache cares about its result, so it skips
 * invalidation entirely.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, type ComputedRef, type MaybeRef, unref } from "vue";
import type { EventCreate, EventOut, EventStats, SignupSummary } from "@/api/types";
import { get, post, put } from "@/api/client";

export type { EventCreate, EventOut, EventStats, SignupSummary };

export function useEventList(enabled?: MaybeRef<boolean>) {
  return useQuery({
    queryKey: ["events", "active"],
    queryFn: () => get<EventOut[]>("/api/v1/events"),
    enabled: computed(() => unref(enabled) ?? true),
  });
}

export function eventList(
  query: ReturnType<typeof useEventList>,
): ComputedRef<EventOut[]> {
  return computed(() => query.data.value ?? []);
}

export function useArchivedEvents() {
  return useQuery({
    queryKey: ["events", "archived"],
    queryFn: () => get<EventOut[]>("/api/v1/events/archived"),
  });
}

export function useEventBySlug(slug: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ["events", "by-slug", unref(slug)] as const),
    queryFn: () => get<EventOut>(`/api/v1/events/by-slug/${unref(slug)}`),
  });
}

export function useEventStats(eventId: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ["events", unref(eventId), "stats"] as const),
    queryFn: () => get<EventStats>(`/api/v1/events/${unref(eventId)}/stats`),
  });
}

export function useEventSignups(eventId: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ["events", unref(eventId), "signups"] as const),
    queryFn: () => get<SignupSummary[]>(`/api/v1/events/${unref(eventId)}/signups`),
  });
}

const invalidateLists = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ queryKey: ["events"] });

export function useCreateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EventCreate) =>
      post<EventOut>("/api/v1/events", payload),
    onSettled: () => invalidateLists(qc),
  });
}

export function useUpdateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; payload: EventCreate }) =>
      put<EventOut>(`/api/v1/events/${vars.eventId}`, vars.payload),
    onSettled: () => invalidateLists(qc),
  });
}

export function useArchiveEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => post(`/api/v1/events/${eventId}/archive`),
    onMutate: async (eventId) => {
      await qc.cancelQueries({ queryKey: ["events", "active"] });
      const snap = qc.getQueryData<EventOut[]>(["events", "active"]);
      qc.setQueryData<EventOut[]>(["events", "active"], (old) =>
        old?.filter((e) => e.id !== eventId),
      );
      return { snap };
    },
    onError: (_err, _id, ctx) =>
      qc.setQueryData(["events", "active"], ctx?.snap),
    onSettled: () => invalidateLists(qc),
  });
}

export function useRestoreEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) =>
      post<EventOut>(`/api/v1/events/${eventId}/restore`),
    onSettled: () => invalidateLists(qc),
  });
}

export function useSendEmailsNow() {
  return useMutation({
    mutationFn: (vars: { eventId: string; channel: "reminder" | "feedback" }) =>
      post<{ processed: number }>(
        `/api/v1/events/${vars.eventId}/send-emails/${vars.channel}`,
      ),
  });
}

export type SignupPayload = {
  display_name: string | null;
  party_size: number;
  source_choice: string | null;
  help_choices: string[];
  email: string | null;
};

export function usePublicSignup() {
  return useMutation({
    mutationFn: (vars: { slug: string; payload: SignupPayload }) =>
      post(`/api/v1/events/by-slug/${vars.slug}/signups`, vars.payload),
  });
}
