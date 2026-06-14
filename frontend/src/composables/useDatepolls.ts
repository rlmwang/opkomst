/**
 * Datepoll composables.
 *
 * Dates-only availability polls that mirror the events/forms
 * resource: chapter-scoped CRUD with active/archived lifecycle,
 * public-by-slug submission, per-date response aggregates.
 *
 * Reads ride ``useApiQuery``; writes invalidate the affected list
 * caches. Mirrors ``useForms.ts`` one-to-one.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { type MaybeRef, unref } from "vue";

import { del, get, post, put } from "@/api/client";
import { listOf, useApiQuery } from "@/api/queries";
import type {
  DatepollCreate,
  DatepollListOut,
  DatepollOut,
  DatepollSlotOut,
  DatepollSubmission,
  DatepollSummary,
  DatepollUpdate,
  PublicDatepollOut,
} from "@/api/types";

export type {
  DatepollCreate,
  DatepollListOut,
  DatepollOut,
  DatepollSlotOut,
  DatepollSubmission,
  DatepollSummary,
  DatepollUpdate,
  PublicDatepollOut,
};

const invalidateLists = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ queryKey: ["datepolls"] });

// --- Reads ---------------------------------------------------------

export function useDatepollList(
  opts: {
    enabled?: MaybeRef<boolean>;
    chapterId?: MaybeRef<string | null>;
  } = {},
) {
  return useApiQuery<DatepollListOut[]>(
    () => ["datepolls", "active", { chapter: unref(opts.chapterId) ?? null }],
    () => {
      const cid = unref(opts.chapterId);
      return cid
        ? `/api/v1/datepolls?chapter_id=${encodeURIComponent(cid)}`
        : "/api/v1/datepolls";
    },
    { enabled: opts.enabled },
  );
}

export const datepollList = listOf<DatepollListOut>;

export function useArchivedDatepolls(
  opts: { chapterId?: MaybeRef<string | null> } = {},
) {
  return useApiQuery<DatepollListOut[]>(
    () => ["datepolls", "archived", { chapter: unref(opts.chapterId) ?? null }],
    () => {
      const cid = unref(opts.chapterId);
      return cid
        ? `/api/v1/datepolls/archived?chapter_id=${encodeURIComponent(cid)}`
        : "/api/v1/datepolls/archived";
    },
  );
}

export function useDatepoll(datepollId: MaybeRef<string>) {
  return useApiQuery<DatepollOut>(
    () => ["datepolls", "single", unref(datepollId)],
    () => `/api/v1/datepolls/${unref(datepollId)}`,
  );
}

export function useDatepollSummary(datepollId: MaybeRef<string>) {
  return useApiQuery<DatepollSummary>(
    () => ["datepolls", unref(datepollId), "summary"],
    () => `/api/v1/datepolls/${unref(datepollId)}/summary`,
  );
}

/** Per-submission rows — CSV source. One-shot fetch, not a query. */
export function fetchDatepollSubmissions(datepollId: string) {
  return get<DatepollSubmission[]>(`/api/v1/datepolls/${datepollId}/submissions`);
}

// --- Public read (by slug) -----------------------------------------

export function usePublicDatepoll(slug: MaybeRef<string>, enabled?: MaybeRef<boolean>) {
  return useApiQuery<PublicDatepollOut>(
    () => ["datepolls", "by-slug", unref(slug)],
    () => `/api/v1/datepolls/by-slug/${encodeURIComponent(unref(slug))}`,
    { enabled },
  );
}

// --- Writes --------------------------------------------------------

export function useCreateDatepoll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DatepollCreate) => post<DatepollOut>("/api/v1/datepolls", payload),
    onSettled: () => invalidateLists(qc),
  });
}

export function useUpdateDatepoll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { datepollId: string; payload: DatepollUpdate }) =>
      put<DatepollOut>(`/api/v1/datepolls/${vars.datepollId}`, vars.payload),
    onSettled: () => invalidateLists(qc),
  });
}

export function useArchiveDatepoll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datepollId: string) => post<DatepollOut>(`/api/v1/datepolls/${datepollId}/archive`),
    onSettled: () => invalidateLists(qc),
  });
}

export function useRestoreDatepoll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datepollId: string) => post<DatepollOut>(`/api/v1/datepolls/${datepollId}/restore`),
    onSettled: () => invalidateLists(qc),
  });
}

export function useDeleteDatepoll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datepollId: string) => del<void>(`/api/v1/datepolls/${datepollId}`),
    onSettled: () => invalidateLists(qc),
  });
}
