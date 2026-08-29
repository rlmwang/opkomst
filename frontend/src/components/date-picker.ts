/**
 * The date picker's arithmetic, without the drawing: the ISO and month
 * keys, the six-week grid, and the format the call sites write dates in.
 *
 * Split out of ``DatePicker`` when the front end started moving to
 * Svelte (``docs/tasks/svelte``), because for a while the same picker is
 * drawn twice, by the organiser's Vue component and by the public chore
 * page's Svelte one, and two copies of a date parser is two copies that
 * drift. The reasoning lives with the components; this is what they both
 * run.
 *
 * ``formatTime`` and ``parseTime`` take the hour format and the currently
 * selected date as arguments rather than reading a prop, which is the
 * only change from the originals.
 */

export function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function monthKeyOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
export interface Cell {
  date: Date;
  iso: string;
  day: number;
  otherMonth: boolean;
}
/** PrimeVue's ``formatDate`` for the tokens this app uses. */
export function formatDate(date: Date, format: string): string {
  let out = "";
  for (let i = 0; i < format.length; i++) {
    const c = format[i];
    const doubled = format[i + 1] === c;
    if (c === "d") {
      out += doubled ? String(date.getDate()).padStart(2, "0") : String(date.getDate());
      if (doubled) i++;
    } else if (c === "m") {
      out += doubled ? String(date.getMonth() + 1).padStart(2, "0") : String(date.getMonth() + 1);
      if (doubled) i++;
    } else if (c === "y") {
      // ``yy`` is the four-digit year, ``y`` the last two. PrimeVue
      // inherited that from jQuery UI and the call sites rely on it.
      out += doubled ? String(date.getFullYear()) : String(date.getFullYear() % 100).padStart(2, "0");
      if (doubled) i++;
    } else {
      out += c;
    }
  }
  return out;
}

export function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatTime(date: Date, hourFormat: "12" | "24"): string {
  if (hourFormat === "12") {
    const h = date.getHours() % 12 || 12;
    return `${pad(h)}:${pad(date.getMinutes())} ${date.getHours() < 12 ? "AM" : "PM"}`;
  }
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Read back what the format writes. Anything that does not parse to a
 *  real date leaves the model alone, so a half-typed day is not a
 *  deletion. */
export function parseDate(text: string, format: string): Date | null {
  const order: string[] = [];
  for (let i = 0; i < format.length; i++) {
    const c = format[i];
    if (c === "d" || c === "m" || c === "y") {
      order.push(c);
      while (format[i + 1] === c) i++;
    }
  }
  const parts = text.split(/\D+/).filter(Boolean);
  if (parts.length !== order.length) return null;
  let day = 1;
  let month = 1;
  let year = new Date().getFullYear();
  order.forEach((token, i) => {
    const n = Number(parts[i]);
    if (token === "d") day = n;
    else if (token === "m") month = n;
    else year = parts[i].length <= 2 ? 2000 + n : n;
  });
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
}

export function parseTime(text: string, from: Date | null): Date | null {
  const m = /^(\d{1,2})[:.](\d{1,2})/.exec(text.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  const base = from ? new Date(from) : new Date();
  base.setHours(h, min, 0, 0);
  return base;
}

/**
 * Six weeks, always, so the panel does not change height between
 * months. Leading and trailing days from the neighbouring months are
 * shown but not selectable, which is PrimeVue's ``showOtherMonths``
 * without ``selectOtherMonths``.
 */
export function monthWeeks(viewMonth: string): Cell[][] {
  const year = Number(viewMonth.split("-")[0]);
  const monthIdx = Number(viewMonth.split("-")[1]) - 1;
  const first = new Date(year, monthIdx, 1);
  const lead = (first.getDay() + 6) % 7;
  const start = new Date(year, monthIdx, 1 - lead);
  const out: Cell[][] = [];
  for (let w = 0; w < 6; w++) {
    const row: Cell[] = [];
    for (let d = 0; d < 7; d++) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d);
      row.push({ date, iso: isoOf(date), day: date.getDate(), otherMonth: date.getMonth() !== monthIdx });
    }
    out.push(row);
  }
  return out;
}

