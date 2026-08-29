import { createI18n } from "vue-i18n";
import { APP_NAME } from "@/lib/branding";
import { captureMessage } from "@/lib/sentry";
import nl from "@/locales/nl.json";

export type Locale = "nl" | "en";
const STORAGE_KEY = "locale";

// The default language is bundled; every other one is fetched when
// somebody asks for it. The two catalogues are 91 kB of JSON between
// them and an organiser reads one, so shipping both in the entry chunk
// wasted half of it on every page of the app.
//
// Bundling the default rather than fetching both is what keeps this off
// the critical path. A fetched catalogue cannot start downloading until
// the entry chunk has parsed, and the app cannot render until it lands,
// so making everyone wait a round trip to save 10 kB is a bad trade. An
// organiser reading English pays that round trip once and the browser
// caches it; an organiser reading Dutch, which is the default and the
// primary audience, pays nothing and still does not download English.
//
// The catalogues carry the same 905 keys, so this does not quietly
// change what renders. If they ever drift, a key the active language is
// missing now reaches ``missingKeyHandler`` instead of silently
// resolving through ``fallbackLocale`` to the Dutch string, which is
// what that handler exists to catch.
const DEFAULT_LOCALE = "nl" as const;
// The bundled catalogue is the shape every other one has to match. The
// two are checked against each other by the compiler because of this,
// which is a free version of the key-parity check.
type Catalogue = typeof nl;
const FETCHED: Partial<Record<Locale, () => Promise<{ default: Catalogue }>>> = {
  en: () => import("@/locales/en.json"),
};
const loaded = new Set<Locale>([DEFAULT_LOCALE]);

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
      captureMessage(`i18n missing key: ${locale}/${key}`, "warning");
    }
  }
  return `[${key}]`;
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: "nl",
  // ``appName`` is injected here so messages can interpolate it with
  // ``@:appName`` rather than every ``t()`` call passing it; single
  // source of truth in ``lib/branding``.
  //
  // The fetched languages are named with an empty catalogue so the
  // locale type stays the full union and ``setLocaleMessage`` is checked
  // against the bundled shape. Empty is the truth until ``loadLocale``
  // has run, and nothing reads a language before that: ``setLocale``
  // waits for the fetch before it switches.
  messages: {
    nl: { ...nl, appName: APP_NAME },
    en: {} as Catalogue & { appName: string },
  },
  // ``missingWarn: false`` to silence vue-i18n's internal warning
  // — our handler already emits a richer one. ``fallbackWarn:
  // false`` for the same reason on the fallback path.
  missingWarn: false,
  fallbackWarn: false,
  missing: missingKeyHandler,
});

/** Fetch one catalogue and hand it to vue-i18n, once. Returns straight
 *  away for the bundled default, which is the common case. */
export async function loadLocale(locale: Locale): Promise<void> {
  if (loaded.has(locale)) return;
  const fetchCatalogue = FETCHED[locale];
  if (!fetchCatalogue) return;
  const catalogue = await fetchCatalogue();
  i18n.global.setLocaleMessage(locale, { ...catalogue.default, appName: APP_NAME });
  loaded.add(locale);
}

/** Have the language the app is starting in before anything renders, so
 *  no screen paints with ``[key]`` in it. Nothing to wait for unless the
 *  organiser reads something other than the default. */
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
