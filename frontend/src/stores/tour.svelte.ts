import { scoped } from "@/composables/useFormDraft.svelte";
import { resolve } from "@/tours/anchors.svelte";
import { TOURS } from "@/tours/tours";
import type { ResolvedStep, Tour, TourId } from "@/tours/types";

/**
 * The tour that is running, if one is (``docs/design-tour.md``
 * chapter 8). A module with getters, the way the session is.
 *
 * Written to session storage on every change and read at boot, so a
 * tour survives the navigation it asks for: the router loads a chunk
 * and swaps the page, the overlay re-renders, and the tour is at the
 * next step. Session rather than local storage, so a tour left
 * half-done is gone when the tab closes.
 */

interface Running {
  tour: TourId;
  product: string | null;
  index: number;
  /** The path the tour was started on. A per-page step runs here. */
  startedOn: string;
  /** The steps that will show. A per-page tour drops the absent ones
   *  when it starts; a cross-page tour keeps its declared list. */
  steps: ResolvedStep[];
  /** Where focus goes back to when the tour ends. Not persisted. */
  opener?: HTMLElement;
}

const KEY = scoped("tour");

function read(): Running | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Omit<Running, "opener">;
    if (!(parsed.tour in TOURS)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function write(value: Running | null): void {
  try {
    if (value === null) sessionStorage.removeItem(KEY);
    else {
      const { opener: _opener, ...rest } = value;
      sessionStorage.setItem(KEY, JSON.stringify(rest));
    }
  } catch {
    /* session storage disabled: the tour lives for this page only */
  }
}

let running = $state<Running | null>(read());

function set(next: Running | null): void {
  running = next;
  write(next);
}

/** The steps a tour will show when started on ``path``: the declared
 *  list for a cross-page tour, and for a per-page tour the ones whose
 *  control is on the page right now. */
function resolveSteps(tour: Tour, path: string): ResolvedStep[] {
  const numbered = tour.steps.map((s, i) => ({ ...s, n: i + 1 }));
  if (!tour.perPage) return numbered;
  return numbered.filter((s) => resolve(s.anchor) !== undefined).map((s) => ({ ...s, page: path }));
}

export const tour = {
  get active() {
    return running !== null;
  },
  get id() {
    return running?.tour ?? null;
  },
  get product() {
    return running?.product ?? null;
  },
  get index() {
    return running?.index ?? 0;
  },
  get steps(): ResolvedStep[] {
    return running?.steps ?? [];
  },
  get step(): ResolvedStep | null {
    return running?.steps[running.index] ?? null;
  },
  get previous(): ResolvedStep | null {
    return running && running.index > 0 ? (running.steps[running.index - 1] ?? null) : null;
  },
  get opener() {
    return running?.opener;
  },
};

/** Start a tour on the page the person is on. ``opener`` is what gets
 *  focus back when it ends. Nothing starts if the tour has no step
 *  that can show. */
export function start(id: TourId, path: string, product: string | null = null, opener?: HTMLElement): boolean {
  const steps = resolveSteps(TOURS[id], path);
  if (steps.length === 0) return false;
  set({ tour: id, product, index: 0, startedOn: path, steps, opener });
  return true;
}

export function next(): void {
  if (!running) return;
  if (running.index + 1 >= running.steps.length) {
    stop();
    return;
  }
  set({ ...running, index: running.index + 1 });
}

export function back(): void {
  if (!running || running.index === 0) return;
  set({ ...running, index: running.index - 1 });
}

/** Drop the current step without showing it: its control is not on
 *  the page. Ends the tour when it was the last one. */
export function skip(): void {
  if (!running) return;
  const current = running;
  const steps = current.steps.filter((_, i) => i !== current.index);
  if (current.index >= steps.length) {
    stop();
    return;
  }
  set({ ...current, steps });
}

export function stop(): void {
  const opener = running?.opener;
  set(null);
  opener?.focus({ preventScroll: true });
}
