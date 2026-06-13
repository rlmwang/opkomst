/**
 * Shared wiring for an archived-list page (archived events, archived
 * forms). Both pages are the same machine — a chapter-filtered list
 * of soft-archived rows with a restore button and a guarded
 * hard-delete — over different resources. Only the row template and
 * the i18n namespace differ, so the page keeps the template and hands
 * the rest here.
 *
 * The i18n key suffixes are identical across resources
 * (``{prefix}.restored`` / ``.restoreFail`` / ``.deleteOk`` /
 * ``.deleteFail`` / ``.deleteConfirmTitle`` / ``.deleteConfirmBody`` /
 * ``.delete`` / ``.loadFailed``); only the ``prefix`` differs
 * (``"archived"`` vs ``"forms.archived"``).
 */

import type { UseMutationReturnType } from "@tanstack/vue-query";
import { type ComputedRef, type Ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";

import { useChapterUrlFilter } from "@/composables/useChapterUrlFilter";
import { useGuardedMutation } from "@/composables/useGuardedMutation";
import { useToasts } from "@/lib/toasts";

interface ListQuery<T> {
  data: Ref<T[] | undefined>;
  isPending: Ref<boolean>;
  isError: Ref<boolean>;
}

// Generic over the two mutations' data/error types so the concrete
// vue-query return types flow straight through to ``useGuardedMutation``
// — re-typing them to a widened ``unknown`` shape trips vue-query's
// discriminated-union variance. ``T`` and all four mutation type args
// are inferred from the arguments (no explicit type args at the call
// site).
export function useArchivedList<T extends { id: string; name: string }, RD, RE, DD, DE>(opts: {
  /** Built with the chapter filter this composable owns, so the query
   * key tracks the dropdown. */
  query: (chapterFilter: ComputedRef<string | null>) => ListQuery<T>;
  restore: UseMutationReturnType<RD, RE, string, unknown>;
  remove: UseMutationReturnType<DD, DE, string, unknown>;
  /** i18n key prefix, e.g. ``"archived"`` or ``"forms.archived"``. */
  prefix: string;
}): {
  chapterFilter: ComputedRef<string | null>;
  setChapterFilter: (value: string | null) => void;
  chapterOptions: ComputedRef<{ id: string; name: string }[]>;
  archived: ComputedRef<T[]>;
  loaded: ComputedRef<boolean>;
  restoreItem: (item: T) => Promise<void>;
  askDelete: (item: T) => Promise<void>;
} {
  const { t } = useI18n();
  const toasts = useToasts();
  const { chapterFilter, setChapterFilter, chapterOptions } = useChapterUrlFilter();

  const query = opts.query(chapterFilter);
  const archived = computed<T[]>(() => query.data.value ?? []);
  const loaded = computed(() => !query.isPending.value);

  watch(query.isError, (isError) => {
    if (isError) toasts.error(t(`${opts.prefix}.loadFailed`));
  });

  async function restoreItem(item: T): Promise<void> {
    try {
      await opts.restore.mutateAsync(item.id);
      toasts.success(t(`${opts.prefix}.restored`, { name: item.name }));
    } catch {
      toasts.error(t(`${opts.prefix}.restoreFail`));
    }
  }

  const askDelete = useGuardedMutation(opts.remove, (item: T) => ({
    vars: item.id,
    ok: t(`${opts.prefix}.deleteOk`, { name: item.name }),
    fail: t(`${opts.prefix}.deleteFail`),
    confirm: {
      header: t(`${opts.prefix}.deleteConfirmTitle`),
      message: t(`${opts.prefix}.deleteConfirmBody`, { name: item.name }),
      icon: "pi pi-exclamation-triangle",
      rejectLabel: t("common.cancel"),
      acceptLabel: t(`${opts.prefix}.delete`),
    },
  }));

  return {
    chapterFilter,
    setChapterFilter,
    chapterOptions,
    archived,
    loaded,
    restoreItem,
    askDelete,
  };
}
