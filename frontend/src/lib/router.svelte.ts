import type { Router } from "vue-router";

/**
 * The router, readable from a Svelte component.
 *
 * There is one router and it is vue-router's, because every page still
 * reaches for it through ``useRouter`` and ``useRoute``. It is the last
 * thing that crosses (``docs/tasks/svelte``), so until it does, the
 * Svelte side reads it here rather than running a second one: two
 * routers over one history is two answers to where the visitor is.
 *
 * ``main.ts`` hands the instance over once, at boot. A component reads
 * ``path`` and gets re-rendered on every navigation, because
 * ``afterEach`` writes it.
 *
 * Temporary: it goes when the route table does.
 */
let instance: Router | null = null;
let current = $state(window.location.pathname);

export function connectRouter(router: Router): void {
  instance = router;
  router.afterEach((to) => {
    current = to.path;
  });
}

/** The path of the route on screen, without the app's base. */
export function routePath(): string {
  return current;
}

export function push(to: string): void {
  void instance?.push(to);
}
