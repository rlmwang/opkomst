/** Short human recurrence hint for an event's list row / detail header,
 * e.g. "Wekelijks · 6 weken" or "Tweewekelijks · doorlopend". A one-off
 * (empty ``cycle_slots``) collapses to a single word. Deliberately coarse:
 * cadence + span only, no per-weekday breakdown (too granular for a card).
 *
 * Takes the vue-i18n ``t`` so callers keep their own locale binding; kept a
 * pure function (no composable) so the dashboard, archive, and detail
 * header all render the hint one way. The rule is the roster's k-week
 * cycle: ``period_weeks`` cadence, ``span_weeks`` span (null = open-ended);
 * ``cycle_slots`` only distinguishes one-off from recurring here. */
type Translate = (key: string, named?: Record<string, unknown>) => string;

interface Rule {
  period_weeks: number;
  cycle_slots: number[];
  span_weeks: number | null;
}

export function recurrenceHint(t: Translate, e: Rule): string {
  if (!e.cycle_slots || e.cycle_slots.length === 0) return t("event.recurrence.oneOff");
  const cadence =
    e.period_weeks === 1
      ? t("event.recurrence.weekly")
      : e.period_weeks === 2
        ? t("event.recurrence.biweekly")
        : t("event.recurrence.everyWeeks", { n: e.period_weeks });
  const span =
    e.span_weeks === null ? t("event.recurrence.openEnded") : t("event.recurrence.weeks", { n: e.span_weeks });
  return `${cadence} · ${span}`;
}
