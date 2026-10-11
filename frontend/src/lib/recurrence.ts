/** Short human recurrence hint for an event's list row / detail header,
 * e.g. "Wekelijks · 6 weken", "Tweewekelijks · 5 sessies" or
 * "Tweewekelijks · doorlopend". A one-off
 * (empty ``cycle_slots``) collapses to a single word. Deliberately coarse:
 * cadence + span only, no per-weekday breakdown (too granular for a card).
 *
 * Takes the vue-i18n ``t`` so callers keep their own locale binding; kept a
 * pure function (no composable) so the dashboard, archive, and detail
 * header all render the hint one way. The rule is the roster's k-week
 * cycle: ``period_weeks`` cadence, and at most one of ``span_weeks``,
 * ``span_sessions`` and ``span_until`` as its end (none = open-ended).
 * Picked dates say how many there are. */
import { localeTag } from "@/lib/format";

type Translate = (key: string, named?: Record<string, unknown>) => string;

interface Rule {
  period_weeks: number;
  cycle_slots: number[];
  picked_dates: string[];
  span_weeks: number | null;
  span_sessions: number | null;
  span_until: string | null;
}

/** More than a one-off: a weekly pattern or a set of picked dates. */
export function isRecurring(e: Pick<Rule, "cycle_slots" | "picked_dates">): boolean {
  return e.cycle_slots.length > 0 || e.picked_dates.length > 0;
}

export function recurrenceHint(t: Translate, e: Rule, locale: string): string {
  if (e.picked_dates.length > 0) return t("event.recurrence.dates", { n: e.picked_dates.length });
  if (e.cycle_slots.length === 0) return t("event.recurrence.oneOff");
  const cadence =
    e.period_weeks === 1
      ? t("event.recurrence.weekly")
      : e.period_weeks === 2
        ? t("event.recurrence.biweekly")
        : t("event.recurrence.everyWeeks", { n: e.period_weeks });
  const span =
    e.span_weeks !== null
      ? t("event.recurrence.weeks", { n: e.span_weeks })
      : e.span_sessions !== null
        ? t("event.recurrence.sessions", { n: e.span_sessions })
        : e.span_until !== null
          ? t("event.recurrence.until", {
              date: new Date(`${e.span_until}T00:00`).toLocaleDateString(localeTag(locale), {
                day: "numeric",
                month: "long",
                year: "numeric",
              }),
            })
          : t("event.recurrence.openEnded");
  return `${cadence} · ${span}`;
}
