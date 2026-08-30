import { apiQuery } from "@/api/queries.svelte";
import type {
  ChoreAccountability,
  ChoreCalendar,
  ChoreSchedule,
  RosterCreate,
  RosterListOut,
  RosterOut,
  RosterUpdate,
  VolunteerSummary,
} from "@/api/types";
import { createEntityCrud } from "@/composables/createEntityCrud.svelte";

/**
 * Chore rosters ("Takenroosters").
 *
 * The chapter-scoped CRUD surface comes from the shared
 * ``createEntityCrud`` factory; what is below it is the roster's own
 * reads.
 */
export type { RosterCreate, RosterListOut, RosterOut, RosterUpdate };

export const rosters = createEntityCrud<RosterListOut, RosterOut, RosterCreate, RosterUpdate>({
  resource: "chore",
});

export function volunteersQuery(rosterId: () => string) {
  return apiQuery<VolunteerSummary[]>(
    () => ["chore", rosterId(), "volunteers"],
    () => `/api/v1/chore/${rosterId()}/volunteers`,
  );
}

export function accountabilityQuery(rosterId: () => string) {
  return apiQuery<ChoreAccountability[]>(
    () => ["chore", rosterId(), "accountability"],
    () => `/api/v1/chore/${rosterId()}/accountability`,
  );
}

export function scheduleQuery(rosterId: () => string) {
  return apiQuery<ChoreSchedule>(
    () => ["chore", rosterId(), "schedule"],
    () => `/api/v1/chore/${rosterId()}/schedule`,
  );
}

/** The roster as a per-chore calendar for one ``YYYY-MM`` month. */
export function calendarQuery(rosterId: () => string, month: () => string, enabled?: () => boolean) {
  return apiQuery<ChoreCalendar[]>(
    () => ["chore", rosterId(), "calendar", month()],
    () => `/api/v1/chore/${rosterId()}/calendar?month=${month()}`,
    { enabled },
  );
}

/** The post-"fold in now" calendar for one month, with changed days
 *  flagged. Fetched only while the fold-in dialog is open. */
export function rebalancePreviewQuery(
  rosterId: () => string,
  month: () => string,
  enabled: () => boolean,
) {
  return apiQuery<ChoreCalendar[]>(
    () => ["chore", rosterId(), "rebalance-preview", month()],
    () => `/api/v1/chore/${rosterId()}/rebalance/preview?month=${month()}`,
    { enabled },
  );
}
