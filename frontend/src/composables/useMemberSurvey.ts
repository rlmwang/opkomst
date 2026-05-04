/**
 * Composables for the new-members feedback survey.
 *
 * One public submit mutation (no auth, used on /s/nieuwe-leden)
 * and one admin-only results query (used on the Feedback tab in
 * the user portal).
 */

import { useMutation } from "@tanstack/vue-query";

import { post } from "@/api/client";
import { useApiQuery } from "@/api/queries";
import type {
  MemberSurveyResults,
  MemberSurveySubmit,
} from "@/api/types";

export type { MemberSurveyResults, MemberSurveySubmit };

export function useMemberSurveyResults() {
  return useApiQuery<MemberSurveyResults>(
    () => ["member-survey", "results"],
    () => "/api/v1/member-survey/results",
  );
}

export function useSubmitMemberSurvey() {
  return useMutation({
    mutationFn: (payload: MemberSurveySubmit) =>
      post<{ status: string }>("/api/v1/member-survey/responses", payload),
  });
}
