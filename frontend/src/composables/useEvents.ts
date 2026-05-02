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
import { type MaybeRef, unref } from "vue";

import { del, post, put } from "@/api/client";
import { listOf, useApiQuery } from "@/api/queries";
import type { EventCreate, EventOut, EventStats, SignupSummary } from "@/api/types";

export type { EventCreate, EventOut, EventStats, SignupSummary };

/** ``chapterId`` is the optional UI filter — ``null`` (or
 * undefined) means "every chapter the user belongs to". The
 * server applies the same predicate; we only ever send the
 * ``chapter_id`` query param when filtering. The query key
 * includes the filter so changing the dropdown produces a fresh
 * cache entry, not a clobber. */
export function useEventList(opts: {
  enabled?: MaybeRef<boolean>;
  chapterId?: MaybeRef<string | null>;
} = {}) {
  return useApiQuery<EventOut[]>(
    () => ["events", "active", { chapter: unref(opts.chapterId) ?? null }],
    () => {
      const cid = unref(opts.chapterId);
      return cid
        ? `/api/v1/events?chapter_id=${encodeURIComponent(cid)}`
        : "/api/v1/events";
    },
    { enabled: opts.enabled },
  );
}

export const eventList = listOf<EventOut>;

export function useArchivedEvents(opts: {
  chapterId?: MaybeRef<string | null>;
} = {}) {
  return useApiQuery<EventOut[]>(
    () => ["events", "archived", { chapter: unref(opts.chapterId) ?? null }],
    () => {
      const cid = unref(opts.chapterId);
      return cid
        ? `/api/v1/events/archived?chapter_id=${encodeURIComponent(cid)}`
        : "/api/v1/events/archived";
    },
  );
}

// ``useEventBySlug`` was removed when /e/:slug moved out of the
// admin SPA into its own mini-app (see ``frontend/public-event.html``
// + ``backend/routers/spa.py``). The mini-app reads
// ``window.__OPKOMST_EVENT__`` injected by the backend; no Vue
// Query, no fetch on first paint.

export function useEventStats(eventId: MaybeRef<string>) {
  return useApiQuery<EventStats>(
    () => ["events", unref(eventId), "stats"],
    () => `/api/v1/events/${unref(eventId)}/stats`,
  );
}

export function useEventSignups(eventId: MaybeRef<string>) {
  return useApiQuery<SignupSummary[]>(
    () => ["events", unref(eventId), "signups"],
    () => `/api/v1/events/${unref(eventId)}/signups`,
  );
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
    // Optimistic patch: the form already has every field that the
    // server will return except the auto-derived ``attendee_count``
    // and ``chapter_name``. Patch the cached row inline so the
    // dashboard / details page show the new values immediately
    // after navigation; the settle invalidation reconciles the
    // derived fields.
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["events", "active"] });
      const snap = qc.getQueryData<EventOut[]>(["events", "active"]);
      qc.setQueryData<EventOut[]>(["events", "active"], (old) =>
        old?.map((e) =>
          e.id === vars.eventId ? { ...e, ...vars.payload } : e,
        ),
      );
      return { snap };
    },
    onError: (_err, _vars, ctx) =>
      qc.setQueryData(["events", "active"], ctx?.snap),
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

export function useDeleteEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => del<void>(`/api/v1/events/${eventId}`),
    // Optimistic drop from the archived list — irreversible action,
    // confirm dialog is the safety gate; cache rollback on error
    // is enough to recover the row visually if the server refuses.
    onMutate: async (eventId) => {
      await qc.cancelQueries({ queryKey: ["events", "archived"] });
      const snap = qc.getQueryData<EventOut[]>(["events", "archived"]);
      qc.setQueryData<EventOut[]>(["events", "archived"], (old) =>
        old?.filter((e) => e.id !== eventId),
      );
      return { snap };
    },
    onError: (_err, _id, ctx) =>
      qc.setQueryData(["events", "archived"], ctx?.snap),
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
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; channel: "reminder" | "feedback" }) =>
      post<{ processed: number }>(
        `/api/v1/events/${vars.eventId}/send-emails/${vars.channel}`,
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

/** Organiser-side hard-delete of one signup row. Optimistically
 * drops the row from the cached signup list; rolls back on error.
 * Stats (total_attendees, by_source, by_help) are derived from
 * signups but live on a separate cache key, so we invalidate that
 * key on settle to keep the headcount honest. */
export function useDeleteSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { eventId: string; signupId: string }) =>
      del<void>(`/api/v1/events/${vars.eventId}/signups/${vars.signupId}`),
    onMutate: async ({ eventId, signupId }) => {
      const key = ["events", eventId, "signups"];
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
      qc.invalidateQueries({ queryKey: ["events", vars.eventId, "signups"] });
      qc.invalidateQueries({ queryKey: ["events", vars.eventId, "stats"] });
    },
  });
}
