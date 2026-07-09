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

// --- Recurring occurrences ---
export type Occurrence = S["OccurrenceOut"];
export type OccurrenceList = S["OccurrenceListOut"];
export type ProjectedOccurrence = S["ProjectedOccurrenceOut"];
export type OccurrenceCard = S["OccurrenceCardOut"];

// --- Public sign-up + booking (also hand-rolled in src/public/api.ts
// for the standalone mini-app bundle; kept here for the admin side). ---
export type PublicEventOut = S["PublicEventOut"];
export type PublicOccurrence = S["PublicOccurrenceOut"];
export type BookingOut = S["BookingOut"];
export type BookingOccurrence = S["BookingOccurrenceOut"];

// --- Forms (standalone questionnaires) ---
export type FormOut = S["FormOut"];
export type FormListOut = S["FormListOut"];
export type FormCreate = S["FormCreate"];
export type FormUpdate = S["FormUpdate"];
export type FormQuestionIn = S["FormQuestionIn"];
export type FormQuestionOut = S["FormQuestionOut"];
export type PublicFormOut = S["PublicFormOut"];
export type FormAnswerIn = S["FormAnswerIn"];
export type FormSubmit = S["FormSubmitIn"];
export type FormSubmitAck = S["FormSubmitAck"];
export type FormQuestionSummary = S["FormQuestionSummary"];
export type FormSummary = S["FormSummaryOut"];
export type FormSubmission = S["FormSubmissionOut"];

// --- Datepolls (date + time-slot availability polls) ---
export type DatepollOut = S["DatepollOut"];
export type DatepollListOut = S["DatepollListOut"];
export type DatepollCreate = S["DatepollCreate"];
export type DatepollUpdate = S["DatepollUpdate"];
export type DatepollSlotIn = S["DatepollSlotIn"];
export type DatepollSlotOut = S["DatepollSlotOut"];
export type PublicDatepollOut = S["PublicDatepollOut"];
export type DatepollSubmit = S["DatepollSubmitIn"];
export type DatepollSummary = S["DatepollSummaryOut"];
export type DatepollSlotSummary = S["DatepollSlotSummary"];
export type DatepollSubmission = S["DatepollSubmissionOut"];

// --- Chores (Dutch: takenroosters) ---
export type RosterOut = S["RosterOut"];
export type RosterListOut = S["RosterListOut"];
export type RosterCreate = S["RosterCreate"];
export type RosterUpdate = S["RosterUpdate"];
export type ChoreIn = S["ChoreIn"];
export type ChoreOut = S["ChoreOut"];
export type PublicRosterOut = S["PublicRosterOut"];
export type VolunteerSummary = S["VolunteerSummaryOut"];
export type ChoreAccountability = S["ChoreAccountabilityOut"];
export type ChoreCalendar = S["ChoreCalendarOut"];
export type CalendarDay = S["CalendarDayOut"];
export type ChoreSchedule = S["ScheduleOut"];
export type ScheduleShift = S["ScheduleShiftOut"];

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
