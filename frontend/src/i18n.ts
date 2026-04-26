import { createI18n } from "vue-i18n";
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

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: "nl",
  messages: { nl, en },
});

export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale;
  localStorage.setItem(STORAGE_KEY, locale);
  document.documentElement.lang = locale;
}

// Sync the <html lang="..."> attribute with the initial locale on load.
document.documentElement.lang = initialLocale();
