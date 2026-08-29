/**
 * Event composables.
 *
 * Reads (list, archived list, by-slug, stats, signups) ride
 * ``useApiQuery`` from ``api/queries``. Writes (create, update,
 * archive, restore, send-emails-now, public signup) are mutations
 * that invalidate the affected lists.
 *
 * The ``signUp`` public mutation talks to a slug-keyed endpoint
 * but no list cache cares about its result, so it skips
 * invalidation entirely.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed, type MaybeRef, unref } from "vue";

import { del, post, postFile, put } from "@/api/client";
import { listOf, useApiQuery } from "@/api/queries";
import { createEntityCrud } from "@/composables/createEntityCrud";
import type {
  EventCreate,
  EventOut,
  EventStats,
  OccurrenceList,
  SignupSummary,
} from "@/api/types";

export type { EventCreate, EventOut, EventStats, OccurrenceList, SignupSummary };

// Events take the shared list/archived/create/restore from the factory
// but keep their own *optimistic* update/archive/delete below (the
// dashboard patches the cache inline; covered by composables.test.ts).
const crud = createEntityCrud<EventOut, EventOut, EventCreate>({ resource: "event" });

/** ``chapterId`` is the optional UI filter — ``null``/undefined means
 * "every chapter the user belongs to"; the filter is in the query key so
 * changing the dropdown produces a fresh cache entry, not a clobber. */
export const useEventList = crud.useList;
export const eventList = listOf<EventOut>;
export const useArchivedEvents = crud.useArchived;

// ``useEventBySlug`` was removed when /e/:slug moved out of the
// admin SPA into its own mini-app (see ``frontend/public-event.html``
// + ``backend/routers/spa.py``). The mini-app reads
// ``window.__OPKOMST_EVENT__`` injected by the backend; no Vue
// Query, no fetch on first paint.

/** The organiser occurrence panel: materialised occurrences with
 * per-session headcount + line-item counts, plus the projected future
 * dates. Replaces the old event-level signups list. */
export function useEventOccurrences(eventId: MaybeRef<string>) {
  return useApiQuery<OccurrenceList>(
    () => ["event", unref(eventId), "occurrences"],
    () => `/api/v1/event/${unref(eventId)}/occurrences`,
  );
}

/** One occurrence's sign-up line items. Enabled only when an
 * ``occurrenceId`` is present so the details page can lazily fetch a
 * panel the organiser expands. */
export function useOccurrenceSignups(
  eventId: MaybeRef<string>,
  occurrenceId: MaybeRef<string | null>,
) {
  return useApiQuery<SignupSummary[]>(
    () => ["event", unref(eventId), "occurrences", unref(occurrenceId), "signups"],
    () =>
      `/api/v1/event/${unref(eventId)}/occurrences/${unref(occurrenceId)}/signups`,
    { enabled: computed(() => Boolean(unref(occurrenceId))) },
  );
}

/** Aggregated source/help breakdown for one occurrence — the "stats of
 * that day" behind the detail page's calendar day switcher. Aggregate
 * only, never linked to a person. Enabled once a day is selected. */
export function useOccurrenceStats(
  eventId: MaybeRef<string>,
  occurrenceId: MaybeRef<string | null>,
) {
  return useApiQuery<EventStats>(
    () => ["event", unref(eventId), "occurrences", unref(occurrenceId), "stats"],
    () =>
      `/api/v1/event/${unref(eventId)}/occurrences/${unref(occurrenceId)}/stats`,
    { enabled: computed(() => Boolean(unref(occurrenceId))) },
  );
}

const invalidateLists = crud.invalidateLists;

export const useCreateEvent = crud.useCreate;

export function useUpdateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; payload: EventCreate }) =>
      put<EventOut>(`/api/v1/event/${vars.eventId}`, vars.payload),
    // Optimistic patch: the form already has every field that the
    // server will return except the auto-derived ``attendee_count``
    // and ``chapter_name``. Patch the cached row inline so the
    // dashboard / details page show the new values immediately
    // after navigation; the settle invalidation reconciles the
    // derived fields.
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["event", "active"] });
      const snap = qc.getQueryData<EventOut[]>(["event", "active"]);
      qc.setQueryData<EventOut[]>(["event", "active"], (old) =>
        old?.map((e) =>
          e.id === vars.eventId ? { ...e, ...vars.payload } : e,
        ),
      );
      return { snap };
    },
    onError: (_err, _vars, ctx) =>
      qc.setQueryData(["event", "active"], ctx?.snap),
    onSettled: () => invalidateLists(qc),
  });
}

/** Upload (or replace) the event's hero image. Returns the
 * server's fresh ``EventOut`` so consumers can patch caches
 * without an extra refetch. Failures bubble up — the page's
 * ``useGuardedMutation`` wrapper renders the toast. */
export function useUploadEventImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; file: File }) =>
      postFile<EventOut>(`/api/v1/event/${vars.eventId}/image`, vars.file),
    onSuccess: (event) => {
      // Patch every list cache in place so the new image_url is
      // visible without waiting for a refetch.
      qc.setQueriesData<EventOut[]>({ queryKey: ["event"] }, (old) =>
        Array.isArray(old) ? old.map((e) => (e.id === event.id ? event : e)) : old,
      );
      qc.setQueryData(["event", "by-slug", event.slug], event);
    },
    onSettled: () => invalidateLists(qc),
  });
}

/** Clear the event's image. The file in the GitHub repo is left
 * alone (see ``backend/services/event_image.py``) — this only
 * nulls ``image_url`` on the row. */
export function useDeleteEventImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => del<EventOut>(`/api/v1/event/${eventId}/image`),
    onSuccess: (event) => {
      qc.setQueriesData<EventOut[]>({ queryKey: ["event"] }, (old) =>
        Array.isArray(old) ? old.map((e) => (e.id === event.id ? event : e)) : old,
      );
      qc.setQueryData(["event", "by-slug", event.slug], event);
    },
    onSettled: () => invalidateLists(qc),
  });
}

export function useArchiveEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => post(`/api/v1/event/${eventId}/archive`),
    onMutate: async (eventId) => {
      await qc.cancelQueries({ queryKey: ["event", "active"] });
      const snap = qc.getQueryData<EventOut[]>(["event", "active"]);
      qc.setQueryData<EventOut[]>(["event", "active"], (old) =>
        old?.filter((e) => e.id !== eventId),
      );
      return { snap };
    },
    onError: (_err, _id, ctx) =>
      qc.setQueryData(["event", "active"], ctx?.snap),
    onSettled: () => invalidateLists(qc),
  });
}

export function useDeleteEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => del<void>(`/api/v1/event/${eventId}`),
    // Optimistic drop from the archived list — irreversible action,
    // confirm dialog is the safety gate; cache rollback on error
    // is enough to recover the row visually if the server refuses.
    onMutate: async (eventId) => {
      await qc.cancelQueries({ queryKey: ["event", "archived"] });
      const snap = qc.getQueryData<EventOut[]>(["event", "archived"]);
      qc.setQueryData<EventOut[]>(["event", "archived"], (old) =>
        old?.filter((e) => e.id !== eventId),
      );
      return { snap };
    },
    onError: (_err, _id, ctx) =>
      qc.setQueryData(["event", "archived"], ctx?.snap),
    onSettled: () => invalidateLists(qc),
  });
}

export const useRestoreEvent = crud.useRestore;

export function useSendEmailsNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; channel: "reminder" | "feedback" }) =>
      post<{ processed: number }>(
        `/api/v1/event/${vars.eventId}/send-emails/${vars.channel}`,
      ),
    // Pending counts in the per-channel summary cards drop after
    // a manual fire — invalidate so the page rerenders without
    // the caller having to chase a refetch.
    onSettled: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
}

// ``usePublicSignup`` + ``SignupPayload`` removed when the public
// sign-up form moved to its own mini-app
// (``frontend/src/public/``). The mini-app uses raw ``fetch``;
// keeping the duplicate type/mutation here would just be dead
// weight in the admin bundle.

/** Organiser-side hard-delete of one sign-up line item. The delete
 * target is the line-item ``id``; ``occurrenceId`` keys the cached
 * per-occurrence list we patch optimistically and roll back on error.
 * Stats (total_attendees, by_source, by_help) and the occurrence
 * panel's per-session counts are derived on separate cache keys, so
 * we invalidate both on settle to keep the headcounts honest. */
export function useDeleteSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; occurrenceId: string; signupId: string }) =>
      del<void>(`/api/v1/event/${vars.eventId}/signups/${vars.signupId}`),
    onMutate: async ({ eventId, occurrenceId, signupId }) => {
      const key = ["event", eventId, "occurrences", occurrenceId, "signups"];
      await qc.cancelQueries({ queryKey: key });
      const snap = qc.getQueryData<SignupSummary[]>(key);
      qc.setQueryData<SignupSummary[]>(key, (old) =>
        old?.filter((s) => s.id !== signupId),
      );
      return { snap, key };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) qc.setQueryData(ctx.key, ctx.snap);
    },
    onSettled: (_data, _err, vars) => {
      qc.invalidateQueries({
        queryKey: ["event", vars.eventId, "occurrences", vars.occurrenceId, "signups"],
      });
      qc.invalidateQueries({ queryKey: ["event", vars.eventId, "occurrences"] });
      qc.invalidateQueries({ queryKey: ["event", vars.eventId, "stats"] });
    },
  });
}
