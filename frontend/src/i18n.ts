import * as Sentry from "@sentry/vue";
import { createI18n } from "vue-i18n";
import { APP_NAME } from "@/lib/branding";

export type Locale = "nl" | "en";
const STORAGE_KEY = "locale";

// One catalogue per language, fetched rather than bundled. The two are
// 91 kB of JSON between them and an organiser reads one of them, so
// shipping both in the entry chunk was half of it wasted on every page
// of the app. Rollup gives each ``import()`` its own chunk; the second
// language is fetched the first time somebody asks for it, and the
// browser caches it from then on.
//
// The catalogues carry the same 905 keys, so this does not quietly
// change what renders. If they ever drift, a key the active language is
// missing now reaches ``missingKeyHandler`` instead of silently
// resolving through ``fallbackLocale`` to the Dutch string, which is
// what that handler exists to catch.
const CATALOGUES: Record<Locale, () => Promise<{ default: Record<string, unknown> }>> = {
  nl: () => import("@/locales/nl.json"),
  en: () => import("@/locales/en.json"),
};
const loaded = new Set<Locale>();

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "nl" || stored === "en") return stored;
  // Default to Dutch — primary audience.
  return "nl";
}

// Tripwire for missing-key bugs. The ``usersTitle`` / ``usersIntro``
// regression was caused by ``t("usersTitle")`` resolving against
// no value and silently rendering the literal string. Default
// vue-i18n behaviour is "warn in dev, silent in prod" — that
// silence is the bug. We replace the handler so:
//
// * dev: ``console.warn`` with a stack pointer at the offending
//   call site, so the developer notices on first render.
// * prod: route to Sentry as a low-severity event so a missed
//   key in a rarely-visited page (e.g. an admin error toast)
//   doesn't sit silently in production until a translator notices.
//
// Returning the bracket-wrapped key ``[admin.usersTitle]`` instead
// of the bare key means a missed key is *visually* obvious in the
// UI too, not blendable with normal copy.
const reported = new Set<string>();
function missingKeyHandler(
  locale: string,
  key: string,
  _instance: unknown,
  _type: unknown,
): string {
  const dedupKey = `${locale}:${key}`;
  if (!reported.has(dedupKey)) {
    reported.add(dedupKey);
    if (import.meta.env.DEV) {
      console.warn(`[i18n] missing key "${key}" in locale "${locale}"`);
    } else {
      Sentry.captureMessage(`i18n missing key: ${locale}/${key}`, "warning");
    }
  }
  return `[${key}]`;
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: "nl",
  // Filled by ``loadLocale`` before the app mounts. Starting empty is
  // what makes the catalogues separate chunks.
  messages: {},
  // ``missingWarn: false`` to silence vue-i18n's internal warning
  // — our handler already emits a richer one. ``fallbackWarn:
  // false`` for the same reason on the fallback path.
  missingWarn: false,
  fallbackWarn: false,
  missing: missingKeyHandler,
});

/** Fetch one catalogue and hand it to vue-i18n, once. ``appName`` is
 *  injected here so messages can interpolate it with ``@:appName``
 *  rather than every ``t()`` call passing it; single source of truth in
 *  ``lib/branding``. */
export async function loadLocale(locale: Locale): Promise<void> {
  if (loaded.has(locale)) return;
  const catalogue = await CATALOGUES[locale]();
  i18n.global.setLocaleMessage(locale, { ...catalogue.default, appName: APP_NAME });
  loaded.add(locale);
}

/** Load the language the app is starting in. ``main.ts`` waits for this
 *  before mounting, so no screen ever paints with ``[key]`` in it. */
export function initI18n(): Promise<void> {
  return loadLocale(initialLocale());
}

export async function setLocale(locale: Locale): Promise<void> {
  await loadLocale(locale);
  i18n.global.locale.value = locale;
  localStorage.setItem(STORAGE_KEY, locale);
  document.documentElement.lang = locale;
}

// Sync the <html lang="..."> attribute with the initial locale on load.
document.documentElement.lang = initialLocale();
