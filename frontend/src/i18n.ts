import { customRef, type Ref } from "vue";

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
 * The translations, as Vue sees them.
 *
 * The catalogues, the lookup and the current language are
 * ``lib/i18n-core``, shared with the Svelte half while the organiser app
 * crosses over (``docs/tasks/svelte``). This file is the thin part: it
 * makes a language change something Vue re-renders on.
 *
 * ``t`` reads ``locale`` before it delegates, which is what puts a
 * template that calls ``t()`` in the language's dependency list. Without
 * that read the string would resolve once and never change again.
 */

/** The language on screen. Writable, because the feedback page adopts
 *  whichever language the event was written in. */
export const locale: Ref<Locale> = customRef((track, trigger) => {
  subscribeLocale(trigger);
  return {
    get() {
      track();
      return currentLocale();
    },
    set(value: Locale) {
      setCurrentLocale(value);
    },
  };
});

export function t(key: string, params?: Record<string, unknown>): string {
  // The read is the point: it is what makes a template that calls
  // ``t()`` re-render when the language changes.
  void locale.value;
  return translate(key, params);
}

/**
 * A string in a named language rather than the one on screen. The event
 * form seeds its default sign-up options in the *event's* language,
 * which is not necessarily the organiser's: picking English in the UI
 * should not lock a Dutch event's options to English.
 */
export function tIn(target: Locale, key: string, params?: Record<string, unknown>): string {
  return translateIn(target, key, params);
}

/** Whether a key resolves at all. Only ``useFormText`` asks. */
export function te(key: string): boolean {
  void locale.value;
  return exists(key);
}

/** The shape every call site destructures. Not a hook: it takes no
 *  arguments and holds no per-component state, and is a function only so
 *  the 58 call sites read the way they always did. */
export function useI18n(): {
  t: typeof t;
  tIn: typeof tIn;
  te: typeof te;
  locale: Ref<Locale>;
} {
  return { t, tIn, te, locale };
}
