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
 *
 * Every key is additionally scoped to the app it was typed in, the
 * same way the session key is: localStorage belongs to the origin, and
 * a half-typed event at the root has no business turning up in an
 * organiser's create form, or the other way round.
 */

import { type MaybeRefOrGetter, toValue, watch, type WatchSource } from "vue";

import { brand, isPersonalApp } from "@/lib/branding";

const APP = isPersonalApp() ? "personal" : brand().slug;

function scoped(key: string): string {
  return `${APP}:${key}`;
}

/** Drop every unsaved draft this app has stored.
 *
 * Called on sign-out. A draft is the previous session's typing, and on
 * a shared browser the next person at the root would otherwise open a
 * create form already filled in with it. */
export function clearAllDrafts(): void {
  try {
    const prefix = `${APP}:`;
    const keys = Object.keys(localStorage).filter((k) => k.startsWith(prefix));
    for (const key of keys) localStorage.removeItem(key);
  } catch {
    // localStorage disabled — nothing to clean up
  }
}

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
      const raw = localStorage.getItem(scoped(toValue(opts.key)));
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      // Unparseable draft, or localStorage disabled — ignore.
      return null;
    }
  }

  function clearDraft(): void {
    try {
      localStorage.removeItem(scoped(toValue(opts.key)));
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
          localStorage.setItem(scoped(toValue(opts.key)), JSON.stringify(opts.snapshot()));
        } catch {
          /* localStorage full or disabled — silently skip */
        }
      }, debounceMs);
    },
    { deep: true },
  );

  return { loadDraft, clearDraft };
}
