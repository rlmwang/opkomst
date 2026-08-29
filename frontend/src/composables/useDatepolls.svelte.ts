import { get } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { createEntityCrud } from "@/composables/createEntityCrud.svelte";
import type {
  DatepollCreate,
  DatepollListOut,
  DatepollOut,
  DatepollSubmission,
  DatepollSummary,
  DatepollUpdate,
  PublicDatepollOut,
} from "@/api/types";

/**
 * Date polls.
 *
 * The chapter-scoped CRUD comes from the shared factory; the summary,
 * the submissions download and the public by-slug read are the poll's
 * own.
 */
export type {
  DatepollCreate,
  DatepollListOut,
  DatepollOut,
  DatepollSubmission,
  DatepollSummary,
  DatepollUpdate,
  PublicDatepollOut,
};

export const datepolls = createEntityCrud<
  DatepollListOut,
  DatepollOut,
  DatepollCreate,
  DatepollUpdate
>({ resource: "datepoll" });

export function datepollSummaryQuery(datepollId: () => string) {
  return apiQuery<DatepollSummary>(
    () => ["datepoll", datepollId(), "summary"],
    () => `/api/v1/datepoll/${datepollId()}/summary`,
  );
}

/** Per-submission rows, the CSV's source. A one-shot fetch, not a
 *  query. */
export function fetchDatepollSubmissions(datepollId: string) {
  return get<DatepollSubmission[]>(`/api/v1/datepoll/${datepollId}/submissions`);
}

export function publicDatepollQuery(slug: () => string, enabled?: () => boolean) {
  return apiQuery<PublicDatepollOut>(
    () => ["datepoll", "by-slug", slug()],
    () => `/api/v1/datepoll/by-slug/${encodeURIComponent(slug())}`,
    { enabled },
  );
}
