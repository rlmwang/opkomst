/**
 * Feedback composables. Reads (form-by-token, preview, summary,
 * submissions) ride ``useApiQuery``; submit is a mutation.
 */

import { useMutation } from "@tanstack/vue-query";
import { type MaybeRef, unref } from "vue";

import { get, post } from "@/api/client";
import { useApiQuery } from "@/api/queries";
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
  return useApiQuery<FeedbackForm>(
    () => ["feedback", "form", unref(token)],
    () => `/api/v1/feedback/${encodeURIComponent(unref(token))}`,
    {
      enabled: enabled ?? Boolean(unref(token)),
      retry: false,
    },
  );
}

export function useFeedbackPreview(
  slug: MaybeRef<string>,
  enabled?: MaybeRef<boolean>,
) {
  return useApiQuery<FeedbackForm>(
    () => ["feedback", "preview", unref(slug)],
    () => `/api/v1/events/by-slug/${encodeURIComponent(unref(slug))}/feedback-preview`,
    {
      enabled: enabled ?? Boolean(unref(slug)),
      retry: false,
    },
  );
}

export function useFeedbackSummary(eventId: MaybeRef<string>) {
  return useApiQuery<FeedbackSummary>(
    () => ["feedback", "summary", unref(eventId)],
    () => `/api/v1/events/${unref(eventId)}/feedback-summary`,
    { retry: false },
  );
}

export async function fetchFeedbackSubmissions(
  eventId: string,
): Promise<FeedbackSubmission[]> {
  return get<FeedbackSubmission[]>(
    `/api/v1/events/${eventId}/feedback-submissions`,
  );
}

export function useSubmitFeedback() {
  // Deliberately no ``onSettled`` invalidation. Submit is a public,
  // one-shot mutation: the server deletes the token row inside the
  // same transaction (privacy contract — no map back to the
  // attendee). A refetch of the form-by-token query immediately
  // 410s, which would beat ``submitted`` in the template and tell
  // the visitor "your link is no longer valid" right after they
  // successfully submitted. Organiser-side feedback-summary is on
  // a different cache key and refreshes on its own staleTime; the
  // organiser doesn't see this submit until they reload anyway.
  return useMutation({
    mutationFn: (vars: { token: string; answers: FeedbackAnswer[] }) =>
      post(`/api/v1/feedback/${encodeURIComponent(vars.token)}/submit`, {
        answers: vars.answers,
      }),
  });
}
