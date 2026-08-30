/**
 * The month grid's arithmetic, without the drawing: the six-week cell
 * list, the column balancing, and the month's own name.
 *
 * Split out of ``MonthGrid`` when the front end started moving to Svelte
 * (``docs/tasks/svelte``), because for a while the same calendar is
 * drawn twice, by the organiser's Vue component and by the public
 * mini-apps' Svelte one, and two copies of the column arithmetic is two
 * copies that drift. The reasoning lives with the components; this is
 * what they both run.
 */

export interface Cell {
  day: number | null;
  iso: string | null;
  today: boolean;
}

export function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** ``en`` and ``nl`` are the two the app names; anything else is already
 *  an Intl tag. */
export function intlLocale(locale: string): string {
  return locale === "en" ? "en-GB" : locale === "nl" ? "nl-NL" : locale;
}

export function monthLabel(month: string, locale: string): string {
  const [year, idx] = month.split("-").map(Number);
  return new Date(year, idx - 1, 1).toLocaleDateString(intlLocale(locale), {
    month: "long",
    year: "numeric",
  });
}

/** The month one step either side, in the same ``YYYY-MM`` form. */
export function shiftMonth(month: string, delta: number): string {
  const [year, idx] = month.split("-").map(Number);
  const d = new Date(year, idx - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Always six weeks, Monday first, so the grid's height never jumps
 *  between months. */
export function monthCells(month: string, todayIso: string): Cell[] {
  const [year, idx] = month.split("-").map(Number);
  const monthIdx = idx - 1;
  const lead = (new Date(year, monthIdx, 1).getDay() + 6) % 7; // Mon = 0
  const dim = new Date(year, monthIdx + 1, 0).getDate();
  const out: Cell[] = Array.from({ length: lead }, () => ({ day: null, iso: null, today: false }));
  for (let d = 1; d <= dim; d++) {
    const iso = `${year}-${String(monthIdx + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    out.push({ day: d, iso, today: iso === todayIso });
  }
  while (out.length < 42) out.push({ day: null, iso: null, today: false });
  return out;
}

/**
 * Most weekday columns are empty (a chore runs on one or two days); the
 * ones that do carry content need room. Each of the seven columns is
 * sized by whether any day in it has content: content columns grow
 * toward 1.5/7, empty ones shrink toward 1/14 (half of 1/7), balanced so
 * the row always sums to full width (fr units, so it stays responsive).
 * Both the header and the grid use this template.
 */
export function columnTemplate(
  cells: Cell[],
  dayClass?: (iso: string) => Record<string, boolean> | undefined,
): string {
  if (!dayClass) return "repeat(7, 1fr)";
  const has = Array<boolean>(7).fill(false);
  cells.forEach((c, i) => {
    if (c.iso && dayClass(c.iso)?.occ) has[i % 7] = true;
  });
  const k = has.filter(Boolean).length;
  if (k === 0 || k === 7) return "repeat(7, 1fr)";
  const MAX = 1.5; // 1.5x 1/7
  const MIN = 0.5; // half 1/7
  const diff = 7 - (k * MAX + (7 - k) * MIN); // slack to balance out to 7 units
  // Slack >= 0: content is capped at MAX, spare width widens the empty
  // columns. Slack < 0: too many content columns to all reach MAX, so
  // they share the deficit (empty columns stay at MIN).
  const content = diff >= 0 ? MAX : MAX + diff / k;
  const empty = diff >= 0 ? MIN + diff / (7 - k) : MIN;
  return has.map((h) => `${(h ? content : empty).toFixed(4)}fr`).join(" ");
}
