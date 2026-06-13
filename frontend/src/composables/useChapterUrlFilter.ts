/**
 * Chapter filter backed by the ``?chapter=`` URL query param.
 *
 * Every chapter-scoped list page (active events / forms, archived
 * events / forms) carries the same filter, and putting it in the URL
 * means the selection survives navigation between the active and
 * archived views of the same resource. Returns the current filter
 * (``null`` = "all chapters") plus a setter that replaces the query
 * param without growing the history stack, and the chapter options
 * the picker renders (the user's own chapters).
 */

import { type ComputedRef, computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

export function useChapterUrlFilter(): {
  chapterFilter: ComputedRef<string | null>;
  setChapterFilter: (value: string | null) => void;
  chapterOptions: ComputedRef<{ id: string; name: string }[]>;
} {
  const route = useRoute();
  const router = useRouter();
  const auth = useAuthStore();

  const chapterFilter = computed<string | null>(() => {
    const v = route.query.chapter;
    return typeof v === "string" && v ? v : null;
  });

  function setChapterFilter(value: string | null): void {
    void router.replace({ query: { ...route.query, chapter: value ?? undefined } });
  }

  const chapterOptions = computed(() => auth.user?.chapters ?? []);

  return { chapterFilter, setChapterFilter, chapterOptions };
}
