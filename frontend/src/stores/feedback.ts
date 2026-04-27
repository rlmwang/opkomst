import { defineStore } from "pinia";
import { ref } from "vue";
import { get, post } from "@/api/client";

export interface FeedbackQuestion {
  id: string;
  ordinal: number;
  kind: "rating" | "text";
  key: string;
  required: boolean;
}

export interface FeedbackForm {
  event_name: string;
  event_slug: string;
  event_locale: "nl" | "en";
  questions: FeedbackQuestion[];
}

export interface FeedbackAnswer {
  question_id: string;
  answer_int?: number | null;
  answer_text?: string | null;
}

export interface FeedbackQuestionSummary {
  question_id: string;
  key: string;
  kind: "rating" | "text";
  response_count: number;
  rating_distribution: number[] | null;
  rating_average: number | null;
  texts: string[] | null;
}

export interface EmailHealth {
  not_applicable: number;
  pending: number;
  sent: number;
  bounced: number;
  complaint: number;
  failed: number;
}

export interface FeedbackSummary {
  submission_count: number;
  signup_count: number;
  response_rate: number;
  email_health: EmailHealth;
  questions: FeedbackQuestionSummary[];
}

export interface FeedbackSubmission {
  submission_id: string;
  answers: Record<string, number | string>;
}

export const useFeedbackStore = defineStore("feedback", () => {
  const questions = ref<FeedbackQuestion[]>([]);

  async function fetchQuestions(): Promise<void> {
    questions.value = await get<FeedbackQuestion[]>("/api/v1/feedback/questions");
  }

  async function getForm(token: string): Promise<FeedbackForm> {
    return get<FeedbackForm>(`/api/v1/feedback/${encodeURIComponent(token)}`);
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

  return { questions, fetchQuestions, getForm, submit, getSummary, getSubmissions };
});
