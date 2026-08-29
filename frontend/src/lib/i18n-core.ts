import { APP_NAME } from "@/lib/branding";
import { captureMessage } from "@/lib/sentry";
import nl from "@/locales/nl.json";

/**
 * The translations, without a framework.
 *
 * Was all of ``src/i18n.ts``, split when the organiser app started
 * crossing to Svelte (``docs/tasks/svelte``): both halves render text
 * from the same catalogues and the same current language, and two
 * copies of that is two languages on one screen. Each side wraps this
 * in its own reactivity and nothing else changes.
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
 * language is missing falls back to the Dutch one, and a key neither has
 * reaches ``reportMissing``.
 */
export type Locale = "nl" | "en";
const STORAGE_KEY = "locale";
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

let current: Locale = initialLocale();
const listeners = new Set<() => void>();

/** The language on screen. */
export function currentLocale(): Locale {
  return current;
}

/** Hear about every language change. Returns the unsubscribe. */
export function subscribeLocale(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

// --- looking a key up ------------------------------------------------
/** Walk ``a.b.c`` down a catalogue. Anything that is not a string at the
 *  end of the walk is a miss, so a key that stops on a branch is
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
 * Returning ``[admin.usersTitle]`` rather than the bare key means a miss
 * is visible on screen too, instead of blending into normal copy.
 */
const reported = new Set<string>();
function reportMissing(key: string): string {
  const dedupKey = `${current}:${key}`;
  if (!reported.has(dedupKey)) {
    reported.add(dedupKey);
    if (import.meta.env.DEV) {
      console.warn(`[i18n] missing key "${key}" in locale "${current}"`);
    } else {
      captureMessage(`i18n missing key: ${current}/${key}`, "warning");
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
 * A string in a named language. The app's name is interpolated into any
 * message that asks for ``{appName}``, so no call site has to pass it.
 *
 * A language whose catalogue has not been fetched yet falls back to the
 * bundled Dutch one, so a caller that needs another language has to have
 * asked ``loadLocale`` for it first.
 */
export function translateIn(
  target: Locale,
  key: string,
  params?: Record<string, unknown>,
): string {
  const message = lookup(catalogues[target], key) ?? lookup(catalogues[DEFAULT_LOCALE], key);
  if (message === undefined) return reportMissing(key);
  return interpolate(message, { appName: APP_NAME, ...params });
}

/** A string in the language on screen. */
export function translate(key: string, params?: Record<string, unknown>): string {
  return translateIn(current, key, params);
}

/** Whether a key resolves at all. Only ``useFormText`` asks, for its
 *  ``<resource>.<key>`` then ``form.<key>`` fallback. */
export function exists(key: string): boolean {
  return (
    lookup(catalogues[current], key) !== undefined ||
    lookup(catalogues[DEFAULT_LOCALE], key) !== undefined
  );
}

// --- languages arriving ----------------------------------------------
/** Install a catalogue for a language. What ``loadLocale`` does with the
 *  one it fetched, and what a test does with the handful of strings the
 *  component under test asks for. */
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
  return loadLocale(current);
}

export async function setLocale(target: Locale): Promise<void> {
  await loadLocale(target);
  setCurrentLocale(target);
  localStorage.setItem(STORAGE_KEY, target);
}

/** Change the language without touching storage: the feedback page
 *  adopts whichever language the event was written in, for that page
 *  only. */
export function setCurrentLocale(target: Locale): void {
  if (current === target) return;
  current = target;
  document.documentElement.lang = target;
  for (const listener of listeners) listener();
}

// Sync the <html lang="..."> attribute with the initial locale on load.
document.documentElement.lang = current;
