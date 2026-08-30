import { auth } from "@/stores/auth.svelte";
import { go, route } from "@/router/navigation.svelte";

/**
 * Chapter filter backed by the ``?chapter=`` URL query parameter.
 *
 * Every chapter-scoped list page carries the same filter, and putting it
 * in the URL means the selection survives navigation between the active
 * and archived views of one resource. ``null`` is every chapter.
 */
export function chapterUrlFilter() {
  return {
    get value(): string | null {
      return route.query.get("chapter") || null;
    },
    set value(next: string | null) {
      const query = new URLSearchParams(route.query);
      if (next) query.set("chapter", next);
      else query.delete("chapter");
      const search = query.toString();
      // Replaced rather than pushed: picking a filter is not a place to
      // come back to with the back button.
      void go(search ? `${route.path}?${search}` : route.path, { replace: true });
    },
    /** The chapters the picker offers: the user's own. */
    get options(): { id: string; name: string }[] {
      return auth.user?.chapters ?? [];
    },
  };
}
