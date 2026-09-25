/**
 * A fake path and a fake count of requests in flight for the engine
 * test to drive. Runes live here because a ``.test.ts`` file cannot
 * hold one.
 */
import { createEngine } from "@/tours/engine.svelte";

let path = $state("/");
let fetching = $state(0);

export const fake = {
  get path() {
    return path;
  },
  set path(next: string) {
    path = next;
  },
  get fetching() {
    return fetching;
  },
  set fetching(next: number) {
    fetching = next;
  },
};

/** An engine on the fake deps, inside an effect root the caller
 *  disposes. */
export function bootEngine() {
  let engine!: ReturnType<typeof createEngine>;
  const dispose = $effect.root(() => {
    engine = createEngine({ path: () => fake.path, fetching: () => fake.fetching });
  });
  return { engine, dispose };
}
