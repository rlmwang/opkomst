import { locale } from "@/i18n.svelte";

/**
 * One field, in two languages, edited through one box.
 *
 * ``value`` reads and writes whichever language the organiser's own
 * interface is in, and ``fallback`` is what the other language
 * currently says, for showing greyed behind an empty box. Flipping the
 * header's language toggle switches which one is being edited, so the
 * same title and description controls do nl and then en without a
 * second widget per field.
 */
export function bilingualField(
  read: () => { nl: string; en: string },
  write: (next: { nl: string; en: string }) => void,
) {
  const isEn = () => locale() === "en";

  return {
    get value(): string {
      const { nl, en } = read();
      return isEn() ? en : nl;
    },
    set value(next: string) {
      const current = read();
      write(isEn() ? { ...current, en: next } : { ...current, nl: next });
    },
    /** What the other language says, or "" when it says nothing. */
    get fallback(): string {
      const { nl, en } = read();
      return isEn() ? nl : en;
    },
  };
}
