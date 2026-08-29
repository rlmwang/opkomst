import { locale, setCatalogue, type Locale } from "@/i18n";

/**
 * Give a test the strings the component under test asks for, and put
 * the app in that language.
 *
 * Was ``createI18n({ messages })`` handed to ``global.plugins``, which
 * ``src/i18n.ts`` no longer needs: the translations are a module, not a
 * Vue plugin, so a test installs a catalogue rather than an app.
 *
 * Vitest gives every test file its own module registry, so a catalogue
 * installed here is not visible to another file. Keys the catalogue
 * does not carry fall back to the bundled Dutch one, which is what the
 * app does.
 */
export function useTestMessages(target: Locale, messages: object): void {
  setCatalogue(target, messages);
  locale.value = target;
}
