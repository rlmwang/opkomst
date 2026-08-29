import { currentPath, subscribeRoute } from "./router-bridge";

export { push } from "./router-bridge";

/**
 * The router, as Svelte sees it.
 *
 * One line of state over ``./router-bridge``, which is where the router
 * itself is held. A component reads ``routePath()`` and is re-rendered
 * on every navigation.
 *
 * Module level rather than per component: there is one location, and a
 * subscription per component would be a subscription per component to
 * tear down.
 *
 * Temporary: it goes when the route table crosses
 * (``docs/tasks/svelte``).
 */
let tracked = $state(currentPath());
subscribeRoute(() => {
  tracked = currentPath();
});

/** The path of the route on screen, without the app's base. */
export function routePath(): string {
  return tracked;
}
