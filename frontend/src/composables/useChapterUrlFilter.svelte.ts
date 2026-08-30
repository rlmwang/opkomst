import { auth } from "@/stores/auth.svelte";
import { go, route } from "@/router/navigation.svelte";

/**
 * What a list page is looking at, backed by the URL: which chapter,
 * which page, and what was typed in the search box.
 *
 * In the URL because a list is a place. The chapter survives moving
 * between the active and archived views of one resource, and page three
 * of a search is a link somebody can send. It is also what the server
 * needs: the list is paged and searched by the database now, so these
 * three are the request.
 */
/** One query parameter, read and written. Replaced rather than pushed:
 *  narrowing a list is not a place to come back to with the back
 *  button. */
function param(name: string) {
  return {
    get(): string | null {
      return route.query.get(name) || null;
    },
    set(next: string | null): void {
      const query = new URLSearchParams(route.query);
      if (next) query.set(name, next);
      else query.delete(name);
      const search = query.toString();
      void go(search ? `${route.path}?${search}` : route.path, { replace: true });
    },
  };
}

export function chapterUrlFilter() {
  const chapter = param("chapter");
  const pageNumber = param("page");
  const search = param("q");
  return {
    get value(): string | null {
      return chapter.get();
    },
    set value(next: string | null) {
      // A different chapter is a different list, so it starts at its
      // first page rather than at whatever number the last one was on.
      pageNumber.set(null);
      chapter.set(next);
    },
    /** Which page of the list is on screen. One-based, absent is one. */
    get page(): number {
      return Number(pageNumber.get() ?? 1);
    },
    set page(next: number) {
      pageNumber.set(next > 1 ? String(next) : null);
    },
    /** What is typed in the search box. Typing starts over at page one:
     *  page three of the old search is not a page of the new one. */
    get search(): string {
      return search.get() ?? "";
    },
    set search(next: string) {
      pageNumber.set(null);
      search.set(next.trim() || null);
    },
    /** The chapters the picker offers: the user's own. */
    get options(): { id: string; name: string }[] {
      return auth.user?.chapters ?? [];
    },
  };
}
