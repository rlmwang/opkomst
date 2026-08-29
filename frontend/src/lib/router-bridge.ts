import type { Router } from "vue-router";

/**
 * Where the visitor is, without a framework.
 *
 * There is one router and it is vue-router's, because every page still
 * reaches for it through ``useRouter`` and ``useRoute``. It is the last
 * thing that crosses (``docs/tasks/svelte``), so until it does, the
 * Svelte side reads it rather than running a second one: two routers
 * over one history is two answers to where the visitor is.
 *
 * Plain rather than runes on purpose, and the Svelte view is
 * ``./router.svelte.ts``. A ``.svelte.ts`` module pulls Svelte's runtime
 * in with it, and importing one from ``main.ts`` put 9.5 kB of it in the
 * organiser's critical path for an adapter no page was using yet.
 *
 * Temporary: it goes when the route table does.
 */
let instance: Router | null = null;
let current = window.location.pathname;
const listeners = new Set<() => void>();

/** Called once by ``main.ts``, which is the only place that has the
 *  router before any page renders. */
export function connectRouter(router: Router): void {
  instance = router;
  router.afterEach((to) => {
    current = to.path;
    for (const listener of listeners) listener();
  });
}

/** The path of the route on screen, without the app's base. */
export function currentPath(): string {
  return current;
}

/** Hear about every navigation. Returns the unsubscribe. */
export function subscribeRoute(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function push(to: string): void {
  void instance?.push(to);
}
