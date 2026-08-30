import { t } from "@/i18n.svelte";
import { chapterUrlFilter } from "@/composables/useChapterUrlFilter.svelte";
import { guarded } from "@/composables/useGuardedMutation.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { useToasts } from "@/lib/toasts";

/**
 * The wiring behind an archived-list page.
 *
 * All four are the same machine over a different resource: a
 * chapter-filtered list of soft-archived rows with a restore button and
 * a guarded hard-delete. Only the row markup and the i18n namespace
 * differ, so a page keeps the markup and hands the rest here.
 *
 * The key suffixes are identical across resources (``{prefix}.restored``,
 * ``.restoreFail``, ``.deleteOk``, ``.deleteFail``,
 * ``.deleteConfirmTitle``, ``.deleteConfirmBody``, ``.delete``); only
 * the prefix differs.
 *
 * The page keeps its own list query, because it renders the rows and
 * has to read them anyway.
 */
interface BilingualName {
  name_nl: string | null;
  name_en: string | null;
}

export interface ArchivedList<T> {
  chapter: { value: string | null; readonly options: { id: string; name: string }[] };
  restoreItem: (item: T) => Promise<void>;
  askDelete: (item: T) => void;
}

export function archivedList<T extends { id: string } & BilingualName>(opts: {
  restore: (id: string) => Promise<unknown>;
  remove: (id: string) => Promise<unknown>;
  /** i18n key prefix, ``"archived"`` or ``"form.archived"``. */
  prefix: string;
}): ArchivedList<T> {
  const toasts = useToasts();
  const chapter = chapterUrlFilter();

  async function restoreItem(item: T): Promise<void> {
    try {
      await opts.restore(item.id);
      toasts.success(t(`${opts.prefix}.restored`, { name: lt(item.name_nl, item.name_en) ?? "" }));
    } catch {
      toasts.error(t(`${opts.prefix}.restoreFail`));
    }
  }

  const askDelete = guarded(opts.remove, (item: T) => ({
    vars: item.id,
    ok: t(`${opts.prefix}.deleteOk`, { name: lt(item.name_nl, item.name_en) ?? "" }),
    fail: t(`${opts.prefix}.deleteFail`),
    confirm: {
      header: t(`${opts.prefix}.deleteConfirmTitle`),
      message: t(`${opts.prefix}.deleteConfirmBody`, {
        name: lt(item.name_nl, item.name_en) ?? "",
      }),
      icon: "exclamation-triangle" as const,
      rejectLabel: t("common.cancel"),
      acceptLabel: t(`${opts.prefix}.delete`),
    },
  }));

  return { chapter, restoreItem, askDelete };
}
