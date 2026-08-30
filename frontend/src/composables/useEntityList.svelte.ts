import { chapterUrlFilter } from "@/composables/useChapterUrlFilter.svelte";
import { guarded } from "@/composables/useGuardedMutation.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { t } from "@/i18n.svelte";

/**
 * The wiring behind a list page.
 *
 * Events, questionnaires, rosters and date polls all list the same way:
 * a chapter-filtered list of cards, each with a details link and an
 * archive button that asks first. Only the copy and the card's middle
 * differ, so a page keeps those and hands the rest here.
 *
 * ``copy`` takes the key inside the page's own namespace, because the
 * forms table's three products resolve a key against their own resource
 * before falling back to the questionnaire's word (``formText``).
 */
interface BilingualName {
  name_nl: string | null;
  name_en: string | null;
}

export interface EntityList<T> {
  chapter: {
    value: string | null;
    page: number;
    search: string;
    readonly options: { id: string; name: string }[];
  };
  askArchive: (item: T) => void;
}

export function entityList<T extends { id: string } & BilingualName>(opts: {
  archive: (id: string) => Promise<unknown>;
  copy: (key: string, params?: Record<string, unknown>) => string;
}): EntityList<T> {
  const { copy } = opts;
  const chapter = chapterUrlFilter();

  const askArchive = guarded(opts.archive, (item: T) => ({
    vars: item.id,
    ok: copy("archived"),
    fail: copy("archiveFail"),
    confirm: {
      header: copy("archiveConfirmTitle"),
      message: copy("archiveConfirmBody", { name: lt(item.name_nl, item.name_en) ?? "" }),
      icon: "exclamation-triangle" as const,
      rejectLabel: t("common.cancel"),
      acceptLabel: copy("archive"),
    },
  }));

  return { chapter, askArchive };
}
