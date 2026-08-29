import { brand, isPersonalApp } from "@/lib/branding";

/**
 * A half-typed form, kept in the browser.
 *
 * Mid-edit state survives a refresh or a closed tab. A page supplies
 * three things: a ``snapshot`` that turns its fields into something
 * JSON can hold, an ``apply`` that puts them back, and a ``track`` that
 * reads every field the draft covers, which is what tells this when to
 * write.
 *
 * The key is a function, so per-entity drafts do not clobber each other:
 * ``chore-edit-draft:abc123`` for an edit page and
 * ``chore-edit-draft:new`` for a create page.
 *
 * Every key is scoped to the app it was typed in, the same way the
 * session key is. localStorage belongs to the origin, and a half-typed
 * event at the root has no business turning up in an organiser's create
 * form, or the other way round.
 */
const APP = isPersonalApp() ? "personal" : brand().slug;

function scoped(key: string): string {
  return `${APP}:${key}`;
}

/**
 * Drop every unsaved draft this app has stored.
 *
 * Called on sign-out. A draft is the previous session's typing, and on
 * a shared browser the next person at the root would otherwise open a
 * create form already filled in with it.
 */
export function clearAllDrafts(): void {
  try {
    const prefix = `${APP}:`;
    for (const key of Object.keys(localStorage).filter((k) => k.startsWith(prefix))) {
      localStorage.removeItem(key);
    }
  } catch {
    /* localStorage disabled: nothing to clean up */
  }
}

export function formDraft<T>(opts: {
  key: () => string;
  snapshot: () => T;
  /** Reads every field the snapshot covers. The effect that saves is
   *  subscribed to whatever this touches, so a field left out of it is
   *  a field that never triggers a save. */
  track: () => unknown;
  debounceMs?: number;
}): { load: () => T | null; clear: () => void } {
  const debounceMs = opts.debounceMs ?? 200;
  let timer: number | null = null;

  function load(): T | null {
    try {
      const raw = localStorage.getItem(scoped(opts.key()));
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      // An unparseable draft, or localStorage disabled.
      return null;
    }
  }

  function clear(): void {
    try {
      localStorage.removeItem(scoped(opts.key()));
    } catch {
      /* localStorage disabled: nothing to clean up */
    }
  }

  $effect(() => {
    opts.track();
    if (timer !== null) clearTimeout(timer);
    timer = window.setTimeout(() => {
      try {
        localStorage.setItem(scoped(opts.key()), JSON.stringify(opts.snapshot()));
      } catch {
        /* localStorage full or disabled */
      }
    }, debounceMs);
    return () => {
      if (timer !== null) clearTimeout(timer);
    };
  });

  return { load, clear };
}
