/**
 * Feedback composables.
 *
 * Replaces ``stores/feedback.ts``. Reads (form-by-token, preview,
 * summary, submissions) are queries; submit is a mutation.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, type MaybeRef, unref } from "vue";
import type {
  EmailChannel,
  EmailHealth,
  FeedbackAnswer,
  FeedbackForm,
  FeedbackQuestion,
  FeedbackQuestionSummary,
  FeedbackSubmission,
  FeedbackSummary,
} from "@/api/types";
import { get, post } from "@/api/client";

export type {
  EmailChannel,
  EmailHealth,
  FeedbackAnswer,
  FeedbackForm,
  FeedbackQuestion,
  FeedbackQuestionSummary,
  FeedbackSubmission,
  FeedbackSummary,
};

export function useFeedbackForm(
  token: MaybeRef<string>,
  enabled?: MaybeRef<boolean>,
) {
  return useQuery({
    queryKey: computed(() => ["feedback", "form", unref(token)] as const),
    queryFn: () =>
      get<FeedbackForm>(`/api/v1/feedback/${encodeURIComponent(unref(token))}`),
    enabled: computed(() => unref(enabled) ?? Boolean(unref(token))),
    retry: false,
  });
}

export function useFeedbackPreview(
  slug: MaybeRef<string>,
  enabled?: MaybeRef<boolean>,
) {
  return useQuery({
    queryKey: computed(() => ["feedback", "preview", unref(slug)] as const),
    queryFn: () =>
      get<FeedbackForm>(
        `/api/v1/events/by-slug/${encodeURIComponent(unref(slug))}/feedback-preview`,
      ),
    enabled: computed(() => unref(enabled) ?? Boolean(unref(slug))),
    retry: false,
  });
}

export function useFeedbackSummary(eventId: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ["feedback", "summary", unref(eventId)] as const),
    queryFn: () =>
      get<FeedbackSummary>(`/api/v1/events/${unref(eventId)}/feedback-summary`),
    retry: false,
  });
}

export async function fetchFeedbackSubmissions(
  eventId: string,
): Promise<FeedbackSubmission[]> {
  return get<FeedbackSubmission[]>(
    `/api/v1/events/${eventId}/feedback-submissions`,
  );
}

export function useSubmitFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { token: string; answers: FeedbackAnswer[] }) =>
      post(`/api/v1/feedback/${encodeURIComponent(vars.token)}/submit`, {
        answers: vars.answers,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
}
