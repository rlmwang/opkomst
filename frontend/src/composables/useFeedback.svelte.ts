import { post } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { mutation } from "@/composables/mutation.svelte";
import type {
  EmailChannel,
  EmailHealth,
  FeedbackAnswer,
  FeedbackForm,
  FeedbackQuestion,
  FeedbackQuestionSummary,
  FeedbackSummary,
} from "@/api/types";

/**
 * The day-after feedback form: the visitor's read of it by token, the
 * organiser's preview and summary, and the one write.
 */
export type {
  EmailChannel,
  EmailHealth,
  FeedbackAnswer,
  FeedbackForm,
  FeedbackQuestion,
  FeedbackQuestionSummary,
  FeedbackSummary,
};

/** The form behind a mailed link. Not retried: the answer to a spent or
 *  unknown token is a message, not another attempt. */
export function feedbackFormQuery(token: () => string, enabled: () => boolean) {
  return apiQuery<FeedbackForm>(
    () => ["feedback", "form", token()],
    () => `/api/v1/feedback/${encodeURIComponent(token())}`,
    { enabled, retry: false },
  );
}

/** The same form, as the organiser sees it before it goes out. */
export function feedbackPreviewQuery(slug: () => string, enabled: () => boolean) {
  return apiQuery<FeedbackForm>(
    () => ["feedback", "preview", slug()],
    () => `/api/v1/event/by-slug/${encodeURIComponent(slug())}/feedback-preview`,
    { enabled, retry: false },
  );
}


/**
 * Submit, and invalidate nothing.
 *
 * The server deletes the token row in the same transaction, because
 * nothing may map an answer back to the person who gave it. A refetch
 * of the form would therefore come back 410 and tell the visitor their
 * link is no longer valid, immediately after they used it. The
 * organiser's summary is a different key on its own stale time.
 */
export const submitFeedback = () =>
  mutation((vars: { token: string; answers: FeedbackAnswer[] }) =>
    post(`/api/v1/feedback/${encodeURIComponent(vars.token)}/submit`, { answers: vars.answers }),
  );
