/**
 * Domain types, re-exported from the auto-generated OpenAPI schema.
 *
 * Single source of truth: backend Pydantic models → ``openapi.json``
 * (committed) → ``schema.ts`` (auto-generated) → these aliases. A
 * field rename in a backend schema breaks every TS consumer the
 * moment ``schema.ts`` is regenerated; CI fails if the generated
 * file drifts from what's committed.
 *
 * The aliases drop the trailing ``Out`` / ``In`` Pydantic suffixes
 * because the frontend doesn't need that distinction — request and
 * response shapes are different types regardless of suffix.
 */

import type { components } from "./schema";

type S = components["schemas"];

// --- Users / auth ---
export type User = S["UserOut"];
export type AuthResponse = S["AuthResponse"];
export type LoginLinkRequest = S["LoginLinkRequest"];
export type LoginRequest = S["LoginRequest"];
export type CompleteRegistrationRequest = S["CompleteRegistrationRequest"];
export type LinkSent = S["LinkSent"];
export type ApproveUserRequest = S["ApproveUserRequest"];
export type SetUserChaptersRequest = S["SetUserChaptersRequest"];
export type ChapterRef = S["ChapterRef"];

// --- Chapters ---
export type Chapter = S["ChapterOut"];
export type ChapterCreate = S["ChapterCreate"];
export type ChapterPatch = S["ChapterPatch"];
export type ChapterArchiveRequest = S["ChapterArchiveRequest"];
export type ChapterUsage = S["ChapterUsageOut"];

// --- Events ---
export type EventOut = S["EventOut"];
export type EventCreate = S["EventCreate"];
export type EventStats = S["EventStatsOut"];
export type SignupSummary = S["SignupSummaryOut"];
export type SignupCreate = S["SignupCreate"];
export type SignupAck = S["SignupAck"];

// --- Feedback ---
export type FeedbackForm = S["FeedbackFormOut"];
export type FeedbackQuestion = S["FeedbackQuestionOut"];
export type FeedbackAnswer = S["FeedbackAnswerIn"];
export type FeedbackSubmit = S["FeedbackSubmitIn"];
export type FeedbackQuestionSummary = S["FeedbackQuestionSummary"];
export type FeedbackSummary = S["FeedbackSummaryOut"];
export type FeedbackSubmission = S["FeedbackSubmissionOut"];
export type EmailHealth = S["EmailHealthOut"];

// --- Channel-keyed maps. The generated schema types EmailHealth as
// the per-channel struct; the FeedbackSummary-side keying lives in
// ``email_health: {[k: string]: EmailHealth}`` which we narrow at
// the consumer site (feedback store knows the keys are
// reminder | feedback). ---
export type EmailChannel = "reminder" | "feedback";
