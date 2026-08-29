/**
 * Warm a row's detail queries while the pointer rests on it.
 *
 * Every list page wants the same thing: by the time a click resolves and
 * the detail page mounts, its queries should already be in cache so the
 * page paints without a skeleton. The naive version fires on
 * ``mouseenter``, which means dragging the pointer down a list of twenty
 * rows requests all twenty. Waiting for the pointer to settle asks only
 * for the row somebody actually stopped on.
 *
 * Each row is asked for once per page visit; ``prefetchQuery`` is itself
 * a no-op while the data is fresh, so the set is belt and braces rather
 * than the only guard.
 */

import { onScopeDispose } from "vue";

/** How long the pointer has to rest before we believe it. Long enough
 *  that crossing a list costs nothing, short enough that it is already
 *  in flight by the time a deliberate hover turns into a click. */
const DWELL_MS = 150;

export function useHoverPrefetch(prefetch: (id: string) => void) {
  const asked = new Set<string>();
  let timer: number | undefined;

  /** Pointer (or focus) landed on a row. */
  function enter(id: string): void {
    if (asked.has(id)) return;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      asked.add(id);
      prefetch(id);
    }, DWELL_MS);
  }

  /** Pointer left before it settled, or moved on to another row. */
  function leave(): void {
    window.clearTimeout(timer);
  }

  onScopeDispose(leave);

  return { enter, leave };
}
