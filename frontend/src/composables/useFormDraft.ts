/**
 * localStorage-backed form draft persistence.
 *
 * Mid-edit form state survives a page refresh (or accidental tab
 * close). The composable wraps three concerns:
 *
 * * ``snapshot()`` — caller-supplied serialiser that captures
 *   every reactive field as a plain JSON-safe object.
 * * ``apply(draft)`` — caller-supplied restorer that writes the
 *   serialised values back into the reactive refs.
 * * ``watchSources`` — the reactive sources to watch; every
 *   change debounces a write to ``localStorage[key.value]``.
 *
 * Returns ``loadDraft()`` and ``clearDraft()`` so the consumer
 * can pull a saved draft on mount and wipe it on save / cancel.
 *
 * The ``key`` is reactive so per-entity drafts don't clobber
 * each other (e.g. ``event-form-draft:abc123`` for the edit
 * page, ``event-form-draft:new`` for the create page).
 */

import { type MaybeRefOrGetter, toValue, watch, type WatchSource } from "vue";

export function useFormDraft<T>(opts: {
  key: MaybeRefOrGetter<string>;
  snapshot: () => T;
  apply: (draft: T) => void;
  sources: WatchSource[];
  debounceMs?: number;
}): {
  loadDraft: () => T | null;
  clearDraft: () => void;
} {
  const debounceMs = opts.debounceMs ?? 200;
  let saveTimer: number | null = null;

  function loadDraft(): T | null {
    try {
      const raw = localStorage.getItem(toValue(opts.key));
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      // Unparseable draft, or localStorage disabled — ignore.
      return null;
    }
  }

  function clearDraft(): void {
    try {
      localStorage.removeItem(toValue(opts.key));
    } catch {
      /* localStorage disabled — nothing to clean up */
    }
  }

  // Debounced write on every reactive change. ``deep: true`` so
  // mutations of nested arrays / objects also fire.
  watch(
    opts.sources,
    () => {
      if (saveTimer !== null) clearTimeout(saveTimer);
      saveTimer = window.setTimeout(() => {
        try {
          localStorage.setItem(toValue(opts.key), JSON.stringify(opts.snapshot()));
        } catch {
          /* localStorage full or disabled — silently skip */
        }
      }, debounceMs);
    },
    { deep: true },
  );

  return { loadDraft, clearDraft };
}
