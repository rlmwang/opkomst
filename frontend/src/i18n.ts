import * as Sentry from "@sentry/vue";
import { createI18n } from "vue-i18n";
import { APP_NAME } from "@/lib/branding";
import en from "@/locales/en.json";
import nl from "@/locales/nl.json";

export type Locale = "nl" | "en";
const STORAGE_KEY = "locale";

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "nl" || stored === "en") return stored;
  // Default to Dutch — primary audience.
  return "nl";
}

// Inject the app name into both locales as ``appName`` so messages
// can interpolate it via ``@:appName`` without each ``t()`` call
// passing it explicitly. Single source of truth in ``lib/branding``.
const messagesWithBranding = {
  nl: { ...nl, appName: APP_NAME },
  en: { ...en, appName: APP_NAME },
};

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
  messages: messagesWithBranding,
  // ``missingWarn: false`` to silence vue-i18n's internal warning
  // — our handler already emits a richer one. ``fallbackWarn:
  // false`` for the same reason on the fallback path.
  missingWarn: false,
  fallbackWarn: false,
  missing: missingKeyHandler,
});

export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale;
  localStorage.setItem(STORAGE_KEY, locale);
  document.documentElement.lang = locale;
}

// Sync the <html lang="..."> attribute with the initial locale on load.
document.documentElement.lang = initialLocale();
