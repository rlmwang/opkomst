/**
 * Form composables.
 *
 * Standalone questionnaires that mirror the events resource:
 * chapter-scoped CRUD with active/archived lifecycle, public-by-
 * slug submission, per-question response aggregates.
 *
 * Reads (list, archived, single, summary, by-slug) ride
 * ``useApiQuery``. Writes (create, update, archive, restore,
 * delete, public submit) are mutations that invalidate the
 * affected list caches.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { type MaybeRef, unref } from "vue";

import { del, get, post, put } from "@/api/client";
import { listOf, useApiQuery } from "@/api/queries";
import type {
  FormCreate,
  FormListOut,
  FormOut,
  FormQuestionIn,
  FormQuestionOut,
  FormSubmit,
  FormSubmitAck,
  FormSubmission,
  FormSummary,
  FormUpdate,
  PublicFormOut,
} from "@/api/types";

export type {
  FormCreate,
  FormListOut,
  FormOut,
  FormQuestionIn,
  FormQuestionOut,
  FormSubmit,
  FormSubmitAck,
  FormSubmission,
  FormSummary,
  FormUpdate,
  PublicFormOut,
};

const invalidateLists = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ queryKey: ["forms"] });

// --- Reads ---------------------------------------------------------

/** Active forms, chapter-scoped. ``chapterId`` (or undefined) =
 * every chapter the user belongs to. The query key includes the
 * filter so changing the dropdown produces a fresh cache entry. */
export function useFormList(
  opts: {
    enabled?: MaybeRef<boolean>;
    chapterId?: MaybeRef<string | null>;
  } = {},
) {
  return useApiQuery<FormListOut[]>(
    () => ["forms", "active", { chapter: unref(opts.chapterId) ?? null }],
    () => {
      const cid = unref(opts.chapterId);
      return cid
        ? `/api/v1/forms?chapter_id=${encodeURIComponent(cid)}`
        : "/api/v1/forms";
    },
    { enabled: opts.enabled },
  );
}

export const formList = listOf<FormListOut>;

export function useArchivedForms(
  opts: { chapterId?: MaybeRef<string | null> } = {},
) {
  return useApiQuery<FormListOut[]>(
    () => ["forms", "archived", { chapter: unref(opts.chapterId) ?? null }],
    () => {
      const cid = unref(opts.chapterId);
      return cid
        ? `/api/v1/forms/archived?chapter_id=${encodeURIComponent(cid)}`
        : "/api/v1/forms/archived";
    },
  );
}

export function useForm(formId: MaybeRef<string>) {
  return useApiQuery<FormOut>(
    () => ["forms", "single", unref(formId)],
    () => `/api/v1/forms/${unref(formId)}`,
  );
}

export function useFormSummary(formId: MaybeRef<string>) {
  return useApiQuery<FormSummary>(
    () => ["forms", unref(formId), "summary"],
    () => `/api/v1/forms/${unref(formId)}/summary`,
  );
}

/** Per-submission rows — CSV source. Not a Vue Query (one-shot
 * download), just a thin fetch helper. */
export function fetchFormSubmissions(formId: string) {
  return get<FormSubmission[]>(`/api/v1/forms/${formId}/submissions`);
}

// --- Public read (by slug) -----------------------------------------

/** Public form fetch. Doesn't require auth. */
export function usePublicForm(slug: MaybeRef<string>, enabled?: MaybeRef<boolean>) {
  return useApiQuery<PublicFormOut>(
    () => ["forms", "by-slug", unref(slug)],
    () => `/api/v1/forms/by-slug/${encodeURIComponent(unref(slug))}`,
    { enabled },
  );
}

// --- Writes --------------------------------------------------------

export function useCreateForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: FormCreate) => post<FormOut>("/api/v1/forms", payload),
    onSettled: () => invalidateLists(qc),
  });
}

export function useUpdateForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { formId: string; payload: FormUpdate }) =>
      put<FormOut>(`/api/v1/forms/${vars.formId}`, vars.payload),
    onSettled: () => invalidateLists(qc),
  });
}

export function useArchiveForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formId: string) => post<FormOut>(`/api/v1/forms/${formId}/archive`),
    onSettled: () => invalidateLists(qc),
  });
}

export function useRestoreForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formId: string) => post<FormOut>(`/api/v1/forms/${formId}/restore`),
    onSettled: () => invalidateLists(qc),
  });
}

export function useDeleteForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formId: string) => del<void>(`/api/v1/forms/${formId}`),
    onSettled: () => invalidateLists(qc),
  });
}

// --- Public submit -------------------------------------------------

export function useSubmitForm() {
  return useMutation({
    mutationFn: (vars: { slug: string; payload: FormSubmit }) =>
      post<FormSubmitAck>(
        `/api/v1/forms/by-slug/${encodeURIComponent(vars.slug)}/submit`,
        vars.payload,
      ),
  });
}
