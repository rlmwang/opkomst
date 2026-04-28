import { defineStore } from "pinia";
import { ref } from "vue";
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

export const useFeedbackStore = defineStore("feedback", () => {
  const questions = ref<FeedbackQuestion[]>([]);

  async function fetchQuestions(): Promise<void> {
    questions.value = await get<FeedbackQuestion[]>("/api/v1/feedback/questions");
  }

  async function getForm(token: string): Promise<FeedbackForm> {
    return get<FeedbackForm>(`/api/v1/feedback/${encodeURIComponent(token)}`);
  }

  async function getPreview(slug: string): Promise<FeedbackForm> {
    return get<FeedbackForm>(
      `/api/v1/events/by-slug/${encodeURIComponent(slug)}/feedback-preview`,
    );
  }

  async function submit(token: string, answers: FeedbackAnswer[]): Promise<void> {
    await post(`/api/v1/feedback/${encodeURIComponent(token)}/submit`, { answers });
  }

  async function getSummary(eventId: string): Promise<FeedbackSummary> {
    return get<FeedbackSummary>(`/api/v1/events/${eventId}/feedback-summary`);
  }

  async function getSubmissions(eventId: string): Promise<FeedbackSubmission[]> {
    return get<FeedbackSubmission[]>(`/api/v1/events/${eventId}/feedback-submissions`);
  }

  return {
    questions,
    fetchQuestions,
    getForm,
    getPreview,
    submit,
    getSummary,
    getSubmissions,
  };
});
