import { auth, fetchMe } from "@/stores/auth.svelte";
import { captureError } from "@/lib/sentry";
import { getToken } from "@/api/client";
import { isPersonalApp } from "@/lib/branding";

import {
  type Matched,
  type PageComponent,
  type RouteDef,
  matchRoute,
  stripBase,
  withBase,
} from "./router.svelte";

/**
 * Where the visitor is, and the one guard that decides whether they may
 * be there.
 *
 * The guard is the same chain vue-router's ``beforeEach`` ran, in the
 * same order, with the same reasoning:
 *
 * Only routes that gate on auth state need to know whether the visitor
 * is signed in. Public routes skip the ``auth/me`` round trip entirely:
 * visitors don't have a JWT and shouldn't pay a network hop to confirm
 * it. ``/`` gates on nothing but renders two different pages depending
 * on whether there is a session, so a held token is resolved even there.
 * No token, no round trip.
 */
let routes: RouteDef[] = [];
let current = $state<Matched | null>(null);
let navigating = $state(false);
let query = $state(new URLSearchParams(window.location.search));

export const route = {
  get path() {
    return current?.path ?? "/";
  },
  get params() {
    return current?.params ?? {};
  },
  get meta() {
    return current?.meta ?? {};
  },
  get component() {
    return current?.component ?? null;
  },
  get query() {
    return query;
  },
  get ready() {
    return current !== null;
  },
  get navigating() {
    return navigating;
  },
};

/** Where the guard sends a visitor who may not be here, or null to let
 *  them through. */
async function redirectFor(meta: RouteDef["meta"]): Promise<string | null> {
  const m = meta ?? {};
  const needsAuth = m.requiresAuth || m.requiresAdmin || m.requiresApproved;
  if ((needsAuth || getToken()) && !auth.loaded) await fetchMe();

  // The root's front door: no session, and the route is one of the
  // create forms. The page posts to ``/api/v1/start/…`` instead of the
  // organiser endpoint and asks for an address on the way out, so there
  // is nothing here to send the visitor back to the door for.
  if (isPersonalApp() && m.startable && !auth.isAuthenticated) return null;

  // The landing page is the door: signed out, it renders the sign-in
  // form itself, so there is no separate login page to send anyone to.
  if (m.requiresAuth && !auth.isAuthenticated) return "/";
  if (m.requiresOrganisation && auth.isPersonal) return "/event";
  if (m.requiresAdmin && !auth.isAdmin) return "/event";
  // Not to /event: that is itself approval-gated, and the landing page
  // is where an account waiting on an admin is told so.
  if (m.requiresApproved && !auth.isApproved) return "/";
  return null;
}

/**
 * Pages are lazy imports. When a chunk fails to load, which is almost
 * always a stale build after a redeploy (the open tab holds an
 * ``index.html`` naming chunk hashes the new build replaced, so the
 * import 404s), the navigation would abort and the view go blank until a
 * manual refresh. Do the refresh instead, landing on the intended path.
 * ``sessionStorage`` guards against a loop if the chunk is genuinely
 * gone rather than merely stale.
 */
function recoverFromStaleChunk(path: string, error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  const stale =
    /dynamically imported module|Importing a module script failed|error loading dynamically imported module|Failed to fetch dynamically imported module/i.test(
      message,
    );
  if (!stale) return false;
  const key = `chunk-reload:${path}`;
  if (sessionStorage.getItem(key)) return true; // already tried, avoid a loop
  sessionStorage.setItem(key, "1");
  window.location.assign(withBase(path));
  return true;
}

/**
 * Go to a path and put something on screen.
 *
 * Something, always. The shell shows a spinner until the first
 * navigation lands, so a path that resolves to nothing is a spinner
 * that never goes away, and this has shipped twice. Every way out of
 * this function either sets ``current``, or hands off to a navigation
 * that will, or reloads the page.
 */
async function land(path: string, search: string, depth = 0): Promise<void> {
  navigating = true;
  try {
    const found = matchRoute(routes, path);
    // The table ends in a catch-all, so this is unreachable. It is
    // handled rather than assumed because the cost of being wrong is a
    // page that never renders.
    if (!found) {
      show(path, search, {}, {}, await notFoundPage());
      return;
    }

    const redirect = await redirectFor(found.route.meta);
    if (redirect !== null && redirect !== path) {
      // A guard sending a visitor to a page whose guard sends them back
      // is a loop, and a loop with an await in it is a hung page. Three
      // hops is more than any chain in the table needs.
      if (depth >= 3) {
        show(path, search, {}, {}, await notFoundPage());
        return;
      }
      window.history.replaceState(null, "", withBase(redirect));
      await land(redirect, "", depth + 1);
      return;
    }

    const module = await found.route.load();
    show(path, search, found.params, found.route.meta ?? {}, module.default);
    // Clear the one-shot reload guard once a navigation actually lands,
    // so a later genuine stale-chunk hit can recover again.
    sessionStorage.removeItem(`chunk-reload:${path}`);
  } catch (error) {
    // A chunk that 404s after a redeploy reloads the page. Anything
    // else is a real fault, and the visitor gets a page saying so
    // rather than a spinner: an error on screen can be reported, and a
    // spinner cannot.
    if (!recoverFromStaleChunk(path, error)) {
      captureError(error);
      show(path, search, {}, {}, await notFoundPage());
    }
  } finally {
    navigating = false;
  }
}

/** The one place ``current`` is written. */
function show(
  path: string,
  search: string,
  params: Record<string, string>,
  meta: RouteDef["meta"],
  component: PageComponent,
): void {
  current = { path, params, meta: meta ?? {}, component };
  query = new URLSearchParams(search);
}

/** What renders when there is nothing else to render. */
const notFoundPage = async (): Promise<PageComponent> =>
  (await import("@/pages/NotFoundPage.svelte")).default;

/** Navigate. ``replace`` swaps the history entry rather than adding
 *  one, which is what a guard's redirect wants. */
export async function go(to: string, opts: { replace?: boolean } = {}): Promise<void> {
  const [path, search = ""] = to.split("?");
  const url = withBase(search ? `${path}?${search}` : path);
  if (opts.replace) window.history.replaceState(null, "", url);
  else window.history.pushState(null, "", url);
  window.scrollTo(0, 0);
  await land(path, search);
}

/** Start routing. Resolves once the first page is on screen, so the
 *  shell can show its loading state until then. */
export async function startRouter(table: RouteDef[]): Promise<void> {
  routes = table;
  window.addEventListener("popstate", () => {
    void land(stripBase(window.location.pathname), window.location.search.slice(1));
  });
  await land(stripBase(window.location.pathname), window.location.search.slice(1));
}
