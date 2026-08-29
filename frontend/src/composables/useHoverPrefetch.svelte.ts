/**
 * Warm a row's detail queries while the pointer rests on it.
 *
 * Every list page wants the same thing: by the time a click resolves and
 * the detail page mounts, its queries are in cache and the page paints
 * without a skeleton. Firing on ``mouseenter`` would request all twenty
 * rows on the way down a list, so the pointer has to settle first.
 *
 * A row is asked for once per visit. ``prefetchQuery`` is itself a no-op
 * while the data is fresh, so the set is belt and braces.
 */
const DWELL_MS = 150;

export function hoverPrefetch(prefetch: (id: string) => void) {
  const asked = new Set<string>();
  let timer: number | undefined;

  function enter(id: string): void {
    if (asked.has(id)) return;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      asked.add(id);
      prefetch(id);
    }, DWELL_MS);
  }

  /** The pointer left before it settled, or moved to another row. */
  function leave(): void {
    window.clearTimeout(timer);
  }

  $effect(() => leave);

  return { enter, leave };
}
