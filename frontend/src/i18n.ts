import { ref, type Ref } from "vue";

import { APP_NAME } from "@/lib/branding";
import { captureMessage } from "@/lib/sentry";
import nl from "@/locales/nl.json";

export type Locale = "nl" | "en";
const STORAGE_KEY = "locale";

/**
 * The organiser app's translations.
 *
 * Was vue-i18n, which is 18,760 gz with @intlify for three things: a
 * dotted-path lookup, ``{brace}`` interpolation, and a language the
 * templates re-read when it changes. The app has no plurals, no date or
 * number formatting and no ``$t`` in any template, so the rest of that
 * library was paid for and never used. The public mini-apps have done
 * it this way since they were written (``src/public/i18n.ts``); this is
 * the organiser app catching up.
 *
 * The catalogues and all 811 call sites are unchanged. ``t``, ``te``,
 * ``locale`` and ``useI18n`` keep the signatures they had.
 *
 * The default language is bundled; every other one is fetched when
 * somebody asks for it. The two catalogues are 91 kB of JSON between
 * them and an organiser reads one, so shipping both in the entry chunk
 * wasted half of it on every page of the app.
 *
 * Bundling the default rather than fetching both is what keeps this off
 * the critical path. A fetched catalogue cannot start downloading until
 * the entry chunk has parsed, and the app cannot render until it lands,
 * so making everyone wait a round trip to save 10 kB is a bad trade. An
 * organiser reading English pays that round trip once and the browser
 * caches it; an organiser reading Dutch, which is the default and the
 * primary audience, pays nothing and still does not download English.
 *
 * The catalogues carry the same 907 keys, so a language switch does not
 * quietly change what renders. If they ever drift, a key the active
 * language is missing falls back to the Dutch one, and a key neither
 * has reaches ``reportMissing``.
 */
const DEFAULT_LOCALE: Locale = "nl";
// The bundled catalogue is the shape every other one has to match. The
// two are checked against each other by the compiler because of this,
// which is a free version of the key-parity check.
type Catalogue = typeof nl;
const FETCHED: Partial<Record<Locale, () => Promise<{ default: Catalogue }>>> = {
  en: () => import("@/locales/en.json"),
};

type Node = string | { [key: string]: Node };
const catalogues: Partial<Record<Locale, Node>> = { nl: nl as Node };

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "nl" || stored === "en") return stored;
  // Default to Dutch, the primary audience.
  return "nl";
}

/** The language on screen. Writable, because the feedback page adopts
 *  whichever language the event was written in. */
export const locale: Ref<Locale> = ref(initialLocale());

// --- looking a key up ------------------------------------------------
/** Walk ``a.b.c`` down a catalogue. Anything that is not a string at
 *  the end of the walk is a miss, so a key that stops on a branch is
 *  reported rather than rendered as "[object Object]". */
function lookup(catalogue: Node | undefined, key: string): string | undefined {
  let cur: Node | undefined = catalogue;
  for (const part of key.split(".")) {
    if (typeof cur !== "object" || cur === null) return undefined;
    cur = cur[part];
  }
  return typeof cur === "string" ? cur : undefined;
}

/**
 * Tripwire for missing-key bugs. The ``usersTitle`` / ``usersIntro``
 * regression was caused by ``t("usersTitle")`` resolving against no
 * value and silently rendering the literal string. vue-i18n's default
 * was "warn in dev, silent in prod", and that silence was the bug.
 *
 * * dev: ``console.warn``, so the developer notices on first render.
 * * prod: a low-severity Sentry event, so a missed key on a rarely
 *   visited page does not sit there until a translator notices.
 *
 * Returning ``[admin.usersTitle]`` rather than the bare key means a
 * miss is visible on screen too, instead of blending into normal copy.
 */
const reported = new Set<string>();
function reportMissing(key: string): string {
  const dedupKey = `${locale.value}:${key}`;
  if (!reported.has(dedupKey)) {
    reported.add(dedupKey);
    if (import.meta.env.DEV) {
      console.warn(`[i18n] missing key "${key}" in locale "${locale.value}"`);
    } else {
      captureMessage(`i18n missing key: ${locale.value}/${key}`, "warning");
    }
  }
  return `[${key}]`;
}

/** ``{name}`` in the string, ``{ name }`` in the params. Anything the
 *  params do not name is left as it is written, so a typo in a
 *  placeholder shows up on screen rather than as an empty gap. */
function interpolate(message: string, params: Record<string, unknown>): string {
  return message.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

/**
 * The app's name is interpolated into any message that asks for
 * ``{appName}``, so no call site has to pass it. Single source of truth
 * in ``lib/branding``.
 */
export function t(key: string, params?: Record<string, unknown>): string {
  // Reading the ref here is what makes every ``t()`` in a template a
  // dependency of the current language, so a switch repaints.
  return tIn(locale.value, key, params);
}

/**
 * A string in a named language rather than the one on screen. The event
 * form seeds its default sign-up options in the *event's* language,
 * which is not necessarily the organiser's: picking English in the UI
 * should not lock a Dutch event's options to English.
 *
 * A language whose catalogue has not been fetched yet falls back to the
 * bundled Dutch one, so a caller that needs another language has to
 * have asked ``loadLocale`` for it first.
 */
export function tIn(target: Locale, key: string, params?: Record<string, unknown>): string {
  const message = lookup(catalogues[target], key) ?? lookup(catalogues[DEFAULT_LOCALE], key);
  if (message === undefined) return reportMissing(key);
  return interpolate(message, { appName: APP_NAME, ...params });
}

/** Whether a key resolves at all. Only ``useFormText`` asks, for its
 *  ``<resource>.<key>`` then ``form.<key>`` fallback. */
export function te(key: string): boolean {
  const active = locale.value;
  return (
    lookup(catalogues[active], key) !== undefined ||
    lookup(catalogues[DEFAULT_LOCALE], key) !== undefined
  );
}

/** The shape every call site destructures. Not a hook: it takes no
 *  arguments and holds no per-component state, and is a function only
 *  so the 58 call sites read the way they always did. */
export function useI18n(): {
  t: typeof t;
  tIn: typeof tIn;
  te: typeof te;
  locale: Ref<Locale>;
} {
  return { t, tIn, te, locale };
}

// --- languages arriving ----------------------------------------------
/** Install a catalogue for a language. What ``loadLocale`` does with
 *  the one it fetched, and what a test does with the handful of strings
 *  the component under test asks for. */
export function setCatalogue(target: Locale, catalogue: object): void {
  catalogues[target] = catalogue as Node;
}

/** Fetch one catalogue, once. Returns straight away for the bundled
 *  default, which is the common case. */
export async function loadLocale(target: Locale): Promise<void> {
  if (catalogues[target]) return;
  const fetchCatalogue = FETCHED[target];
  if (!fetchCatalogue) return;
  const catalogue = await fetchCatalogue();
  setCatalogue(target, catalogue.default);
}

/** Have the language the app is starting in before anything renders, so
 *  no screen paints with ``[key]`` in it. Nothing to wait for unless the
 *  organiser reads something other than the default. */
export function initI18n(): Promise<void> {
  return loadLocale(locale.value);
}

export async function setLocale(target: Locale): Promise<void> {
  await loadLocale(target);
  locale.value = target;
  localStorage.setItem(STORAGE_KEY, target);
  document.documentElement.lang = target;
}

// Sync the <html lang="..."> attribute with the initial locale on load.
document.documentElement.lang = locale.value;
