import { apiQuery } from "@/api/queries.svelte";
import { createEntityCrud } from "@/composables/createEntityCrud.svelte";
import type {
  DatepollCreate,
  DatepollListOut,
  DatepollOut,
  DatepollPage,
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
  DatepollPage,
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

/**
 * Everything the details page draws, in one request: the poll, the
 * tally per date, and the per-person grid under it. Three requests
 * before, all about the same poll.
 */
export function datepollPageQuery(datepollId: () => string) {
  return apiQuery<DatepollPage>(
    () => ["datepoll", datepollId(), "page"],
    () => `/api/v1/datepoll/${datepollId()}/page`,
  );
}

export function publicDatepollQuery(slug: () => string, enabled?: () => boolean) {
  return apiQuery<PublicDatepollOut>(
    () => ["datepoll", "by-slug", slug()],
    () => `/api/v1/datepoll/by-slug/${encodeURIComponent(slug())}`,
    { enabled },
  );
}
