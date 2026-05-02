/** ICU locale tag for the active i18n locale. ``"en"`` → en-GB so
 * dates render as "27 April 2026" rather than US "April 27, 2026". */
export function localeTag(locale: string): string {
  return locale === "en" ? "en-GB" : "nl-NL";
}

/** Long human-readable date: ``maandag 27 april 2026``. */
export function formatDate(iso: string, locale: string): string {
  return new Date(iso).toLocaleDateString(localeTag(locale), {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** Hour:minute range: ``18:00 — 20:00``. */
export function formatTimeRange(startIso: string, endIso: string, locale: string): string {
  const opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };
  const start = new Date(startIso).toLocaleTimeString(localeTag(locale), opts);
  const end = new Date(endIso).toLocaleTimeString(localeTag(locale), opts);
  return `${start} — ${end}`;
}

/** Compact "date + time" used in list rows: ``27-04-2026 18:00``.
 * Seconds are deliberately suppressed — events are scheduled to
 * the minute, never the second, so showing ``18:00:00`` is just
 * noise that erodes typographic rhythm. */
export function formatDateTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(localeTag(locale), {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
