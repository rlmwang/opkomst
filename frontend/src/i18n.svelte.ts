import {
  type Locale,
  currentLocale,
  exists,
  setCurrentLocale,
  subscribeLocale,
  translate,
  translateIn,
} from "@/lib/i18n-core";

export {
  initI18n,
  loadLocale,
  setCatalogue,
  setLocale,
  type Locale,
} from "@/lib/i18n-core";

/**
 * The translations, as Svelte sees them.
 *
 * The catalogues, the lookup and the current language are
 * ``lib/i18n-core``, shared with the Vue half while the organiser app
 * crosses over (``docs/tasks/svelte``). This file is the thin part: it
 * makes a language change something Svelte re-renders on.
 *
 * ``t`` reads the tracked language before it delegates, which is what
 * puts a component that calls ``t()`` in its dependency list. Without
 * that read the string would resolve once and never change again.
 *
 * Module level rather than per component: there is one language, and a
 * subscription per component would be a subscription per component to
 * tear down.
 */
let tracked = $state(currentLocale());
subscribeLocale(() => {
  tracked = currentLocale();
});

/** The language on screen. */
export function locale(): Locale {
  return tracked;
}

/** Adopt a language for this page only, without touching storage. */
export function setPageLocale(target: Locale): void {
  setCurrentLocale(target);
}

export function t(key: string, params?: Record<string, unknown>): string {
  // The read is the point: it is what makes a component that calls
  // ``t()`` re-render when the language changes.
  void tracked;
  return translate(key, params);
}

/** A string in a named language rather than the one on screen. */
export function tIn(target: Locale, key: string, params?: Record<string, unknown>): string {
  return translateIn(target, key, params);
}

/** Whether a key resolves at all. */
export function te(key: string): boolean {
  void tracked;
  return exists(key);
}
