import { del, post, postFile, put } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { createEntityCrud } from "@/composables/createEntityCrud.svelte";
import { mutation } from "@/composables/mutation.svelte";
import { queryClient } from "@/lib/query-client";
import type {
  EventCreate,
  EventListOut,
  EventOut,
  EventStats,
  OccurrenceList,
  SignupSummary,
} from "@/api/types";

/**
 * Events.
 *
 * The chapter-scoped CRUD comes from the shared factory. What is here
 * on top is the event's own reads, and the three writes that patch the
 * cache before the server answers: the organiser sees the row change on
 * the click, and a refusal puts it back.
 */
export type { EventCreate, EventListOut, EventOut, EventStats, OccurrenceList, SignupSummary };

export const events = createEntityCrud<EventListOut, EventOut, EventCreate>({ resource: "event" });

/** The organiser's occurrence panel: materialised occurrences with
 *  per-session headcount and line-item counts, plus the projected
 *  future dates. */
export function occurrencesQuery(eventId: () => string) {
  return apiQuery<OccurrenceList>(
    () => ["event", eventId(), "occurrences"],
    () => `/api/v1/event/${eventId()}/occurrences`,
  );
}

/** One occurrence's sign-up line items. Enabled only once an occurrence
 *  is chosen, so the details page fetches a panel when it is opened. */
export function occurrenceSignupsQuery(eventId: () => string, occurrenceId: () => string | null) {
  return apiQuery<SignupSummary[]>(
    () => ["event", eventId(), "occurrences", occurrenceId(), "signups"],
    () => `/api/v1/event/${eventId()}/occurrences/${occurrenceId()}/signups`,
    { enabled: () => Boolean(occurrenceId()) },
  );
}

/** The source and help breakdown for one occurrence: the "stats of that
 *  day" behind the details page's calendar switcher. Aggregate only,
 *  never linked to a person. */
export function occurrenceStatsQuery(eventId: () => string, occurrenceId: () => string | null) {
  return apiQuery<EventStats>(
    () => ["event", eventId(), "occurrences", occurrenceId(), "stats"],
    () => `/api/v1/event/${eventId()}/occurrences/${occurrenceId()}/stats`,
    { enabled: () => Boolean(occurrenceId()) },
  );
}

/**
 * Update, patched into both caches the organiser is about to look at.
 *
 * The form already holds every field the server will return except the
 * derived ``attendee_count`` and ``chapter_name``, so the new values are
 * on screen before the round trip; the settle invalidation reconciles
 * the derived pair.
 *
 * The two option lists are left out of the patch. An option the
 * organiser has just added has no id until the server gives it one, so
 * writing the form's copy into the cache would put a row there that
 * every other reader believes is saved. They come back with the
 * invalidation, which is one round trip away.
 */
export const updateEvent = () =>
  mutation(
    (vars: { eventId: string; payload: EventCreate }) =>
      put<EventOut>(`/api/v1/event/${vars.eventId}`, vars.payload),
    {
      invalidate: [["event"]],
      optimistic: (vars) => {
        const { source_options, help_options, ...patch } = vars.payload;
        void source_options;
        void help_options;
        const single = ["event", "single", vars.eventId];
        const snapList = queryClient.getQueryData<EventListOut[]>(["event", "active"]);
        const snapSingle = queryClient.getQueryData<EventOut>(single);
        queryClient.setQueryData<EventListOut[]>(["event", "active"], (old) =>
          old?.map((e) => (e.id === vars.eventId ? { ...e, ...patch } : e)),
        );
        if (snapSingle) {
          queryClient.setQueryData<EventOut>(single, { ...snapSingle, ...patch });
        }
        return () => {
          queryClient.setQueryData(["event", "active"], snapList);
          queryClient.setQueryData(single, snapSingle);
        };
      },
    },
  );

/** Upload or replace the event's hero image. Only the single-event
 *  cache is patched: a list row carries no image, so writing the full
 *  event into the list caches would replace a row with a differently
 *  shaped one to no visible end. */
export const uploadEventImage = () =>
  mutation(
    (vars: { eventId: string; file: File }) =>
      postFile<EventOut>(`/api/v1/event/${vars.eventId}/image`, vars.file),
    {
      invalidate: [["event"]],
      onSuccess: (updated, vars) =>
        queryClient.setQueryData(["event", "single", vars.eventId], updated),
    },
  );

export const deleteEventImage = () =>
  mutation((eventId: string) => del<EventOut>(`/api/v1/event/${eventId}/image`), {
    invalidate: [["event"]],
    onSuccess: (updated, eventId) =>
      queryClient.setQueryData(["event", "single", eventId], updated),
  });

/** Archive, dropped from the active list on the click. */
export const archiveEvent = () =>
  mutation((eventId: string) => post(`/api/v1/event/${eventId}/archive`), {
    invalidate: [["event"]],
    optimistic: (eventId) => {
      const snap = queryClient.getQueryData<EventListOut[]>(["event", "active"]);
      queryClient.setQueryData<EventListOut[]>(["event", "active"], (old) =>
        old?.filter((e) => e.id !== eventId),
      );
      return () => queryClient.setQueryData(["event", "active"], snap);
    },
  });

/** Hard delete, dropped from the archived list on the click. The
 *  confirm dialog is the safety gate; the rollback is enough to put the
 *  row back if the server refuses. */
export const deleteEvent = () =>
  mutation((eventId: string) => del<void>(`/api/v1/event/${eventId}`), {
    invalidate: [["event"]],
    optimistic: (eventId) => {
      const snap = queryClient.getQueryData<EventListOut[]>(["event", "archived"]);
      queryClient.setQueryData<EventListOut[]>(["event", "archived"], (old) =>
        old?.filter((e) => e.id !== eventId),
      );
      return () => queryClient.setQueryData(["event", "archived"], snap);
    },
  });

/** Fire a channel's pending mail now. The per-channel summary cards
 *  count what is still owed, so they are invalidated rather than left
 *  for the caller to chase. */
export const sendEmailsNow = () =>
  mutation(
    (vars: { eventId: string; channel: "reminder" | "feedback" }) =>
      post<{ processed: number }>(`/api/v1/event/${vars.eventId}/send-emails/${vars.channel}`),
    { invalidate: [["feedback"]] },
  );

/**
 * Organiser-side hard delete of one sign-up line item.
 *
 * The target is the line item's id; the occurrence keys the cached
 * per-occurrence list that is patched and rolled back. The headcounts
 * and the stats are derived on separate cache keys, so both are
 * invalidated on settle to keep them honest.
 */
export const deleteSignup = () =>
  mutation(
    (vars: { eventId: string; occurrenceId: string; signupId: string }) =>
      del<void>(`/api/v1/event/${vars.eventId}/signups/${vars.signupId}`),
    {
      optimistic: ({ eventId, occurrenceId, signupId }) => {
        const key = ["event", eventId, "occurrences", occurrenceId, "signups"];
        const snap = queryClient.getQueryData<SignupSummary[]>(key);
        queryClient.setQueryData<SignupSummary[]>(key, (old) =>
          old?.filter((s) => s.id !== signupId),
        );
        return () => queryClient.setQueryData(key, snap);
      },
      onSuccess: (_result, vars) => {
        void queryClient.invalidateQueries({
          queryKey: ["event", vars.eventId, "occurrences", vars.occurrenceId, "signups"],
        });
        void queryClient.invalidateQueries({ queryKey: ["event", vars.eventId, "occurrences"] });
        void queryClient.invalidateQueries({ queryKey: ["event", vars.eventId, "stats"] });
      },
    },
  );
