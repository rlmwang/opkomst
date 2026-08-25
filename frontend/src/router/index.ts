import { createRouter, createWebHistory, type RouteLocationNormalized } from "vue-router";
import { getToken } from "@/api/client";
import { brand, isPersonalApp } from "@/lib/branding";
import { useAuthStore } from "@/stores/auth";

const routes = [
  // ``/{tenant}``: the organiser's landing page when signed in, the
  // organisation's public chapter index when not. Deliberately no
  // ``requiresAuth`` — a visitor with no session gets the public face
  // rather than a redirect to the login page.
  { path: "/", component: () => import("@/pages/HomePage.vue") },
  { path: "/login", component: () => import("@/pages/LoginPage.vue") },
  { path: "/register/complete", component: () => import("@/pages/RegisterCompletePage.vue") },
  { path: "/auth/redeem", component: () => import("@/pages/RedeemPage.vue") },
  // Every workspace requires an approved account. An account still
  // waiting on an admin has nothing to do in any of them, and being
  // shown four doors that all open onto "you are not approved yet" is
  // worse than being told once, on the landing page.
  { path: "/events", component: () => import("@/pages/DashboardPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  // ``requiresOrganisation``: these act on an organisation's people and
  // its chapters, and a personal account has neither. The API 404s them
  // for such an account; the guard keeps a typed URL from getting there
  // and finding a page full of errors.
  { path: "/users", component: () => import("@/pages/UsersPage.vue"), meta: { requiresAuth: true, requiresApproved: true, requiresOrganisation: true } },
  { path: "/chapters", component: () => import("@/pages/ChaptersPage.vue"), meta: { requiresAuth: true, requiresApproved: true, requiresOrganisation: true } },
  // ``startable``: at the root these four are also the signed-out
  // front door — a tile on the landing page opens the create form
  // itself, and the address is a field in it rather than a wall in
  // front of it. Under an organisation's slug the flag does nothing,
  // because there the visitor is somebody's organiser or nobody.
  { path: "/events/new", component: () => import("@/pages/EventFormPage.vue"), meta: { requiresAuth: true, requiresApproved: true, startable: true } },
  { path: "/events/:eventId/edit", component: () => import("@/pages/EventFormPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/:eventId/details", component: () => import("@/pages/EventDetailsPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/archived", component: () => import("@/pages/ArchivedEventsPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  // Forms — standalone questionnaires (no relation to Events).
  // Same chapter-scoped four-page experience: active list /
  // archived list / details / edit. The public fill-out lives
  // at /f/:slug and is unauthenticated.
  { path: "/forms", component: () => import("@/pages/FormListPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/forms/archived", component: () => import("@/pages/ArchivedFormsPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/forms/new", component: () => import("@/pages/FormEditPage.vue"), meta: { requiresAuth: true, requiresApproved: true, startable: true } },
  { path: "/forms/:formId/edit", component: () => import("@/pages/FormEditPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/forms/:formId/details", component: () => import("@/pages/FormDetailsPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  // Datepolls — dates-only availability polls (no relation to
  // Events/Forms). Same chapter-scoped four-page experience; the
  // public fill-out lives at /d/:slug and is unauthenticated
  // (served by the backend mini-app, not this router).
  { path: "/datepolls", component: () => import("@/pages/DatepollListPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/datepolls/archived", component: () => import("@/pages/ArchivedDatepollsPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/datepolls/new", component: () => import("@/pages/DatepollEditPage.vue"), meta: { requiresAuth: true, requiresApproved: true, startable: true } },
  { path: "/datepolls/:datepollId/edit", component: () => import("@/pages/DatepollEditPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/datepolls/:datepollId/details", component: () => import("@/pages/DatepollDetailsPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  // Chores (Dutch: takenroosters) — recurring-chore rosters. ``/c/:slug`` public
  // enrol page is a separate backend mini-app (task 07), not here.
  { path: "/chores", component: () => import("@/pages/ChoresListPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/chores/archived", component: () => import("@/pages/ArchivedChoresPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/chores/new", component: () => import("@/pages/ChoresEditPage.vue"), meta: { requiresAuth: true, requiresApproved: true, startable: true } },
  { path: "/chores/:rosterId/edit", component: () => import("@/pages/ChoresEditPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/chores/:rosterId/details", component: () => import("@/pages/ChoresDetailsPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  // ``/f/:slug`` is NOT in the admin SPA router — it's served by
  // the backend as a separate Vue mini-app (``public-form.html``
  // + ``src/public_form/``) with the form payload inlined into
  // the HTML response. Same pattern as ``/e/:slug``; see
  // ``backend/routers/spa.py``.
  // ``/e/:slug`` is no longer in the admin SPA router — it's
  // served by the backend as a separate Vue mini-app
  // (``frontend/public-event.html`` + ``src/public/``) with the
  // event payload inlined into the HTML response. See
  // ``backend/routers/spa.py``. Only the feedback flow is left in
  // the admin bundle because it's a one-off form gated on a
  // single-use token, low traffic.
  { path: "/e/:slug/feedback", component: () => import("@/pages/FeedbackPage.vue"), props: true },
  // Admin-only WhatsApp blast tool (Evolution API proxy).
  // ``requiresWhatsApp`` redirects to /events when the EVOLUTION_*
  // env vars aren't all set on the server, so direct URL pokes
  // don't surface a non-functional page.
  { path: "/admin/whatsapp", component: () => import("@/pages/AdminWhatsAppPage.vue"), meta: { requiresAuth: true, requiresAdmin: true, requiresWhatsApp: true, requiresOrganisation: true } },
  { path: "/:pathMatch(.*)*", component: () => import("@/pages/NotFoundPage.vue") },
];

// The organiser app is served under its organisation's slug
// (``opkomst.nu/rsp/events``), so every route above is relative to that
// base. It comes from the brand the server injected into the page head —
// the app never parses it out of the URL, so a mismatch between what the
// page is wearing and what it routes to is impossible. A page served in
// the house brand belongs to no organisation and is based at ``/``, so
// whatever path the visitor typed falls through to the not-found route.
const router = createRouter({
  history: createWebHistory(brand().app_base),
  routes,
});

router.beforeEach(async (to: RouteLocationNormalized) => {
  const auth = useAuthStore();
  // Only routes that gate on auth state need to know whether the
  // visitor is logged in. Public routes (``/e/:slug``,
  // ``/e/:slug/feedback``, ``/login``, ``/register/complete``) skip the
  // ``auth/me`` round-trip entirely — visitors don't have a JWT
  // and shouldn't pay a network hop to confirm that.
  const needsAuth =
    to.meta.requiresAuth || to.meta.requiresAdmin || to.meta.requiresApproved;
  // ``/{tenant}`` gates on nothing but renders two different pages
  // depending on whether there's a session, so a held token has to be
  // resolved even on routes that don't require one. No token, no
  // round-trip — visitors still pay nothing.
  if ((needsAuth || getToken()) && !auth.loaded) await auth.fetchMe();

  // The root's front door: no session, and the route is one of the
  // four create forms. The page posts to ``/api/v1/start/…`` instead
  // of the organiser endpoint and asks for an address on the way out,
  // so there is nothing here to send the visitor to /login for.
  if (isPersonalApp() && to.meta.startable && !auth.isAuthenticated) return true;

  if (to.meta.requiresAuth && !auth.isAuthenticated) return { path: "/login", query: { next: to.fullPath } };
  if (to.meta.requiresOrganisation && auth.isPersonal) return { path: "/events" };
  if (to.meta.requiresAdmin && !auth.isAdmin) return { path: "/events" };
  // Not to /events: that is itself approval-gated now, and the landing
  // page is where an account waiting on an admin is told so.
  if (to.meta.requiresApproved && !auth.isApproved) return { path: "/" };
  if (to.meta.requiresWhatsApp && !auth.whatsappAvailable) return { path: "/events" };
  return true;
});

// Pages are lazy ``() => import(...)``. When a route's chunk fails to
// load — almost always a stale build after a redeploy: the open tab
// holds an ``index.html`` referencing chunk hashes the new build
// replaced, so the dynamic import 404s — the navigation aborts and
// the view goes blank until a manual refresh. Detect that specific
// failure and do the refresh automatically, landing on the intended
// path. ``sessionStorage`` guards against a reload loop if the chunk
// is genuinely gone (not just stale).
router.onError((error: unknown, to: RouteLocationNormalized) => {
  const message = error instanceof Error ? error.message : String(error);
  const isChunkLoadError =
    /dynamically imported module|Importing a module script failed|error loading dynamically imported module|Failed to fetch dynamically imported module/i.test(
      message,
    );
  if (!isChunkLoadError) return;
  const key = `chunk-reload:${to.fullPath}`;
  if (sessionStorage.getItem(key)) return; // already tried — avoid a loop
  sessionStorage.setItem(key, "1");
  window.location.assign(to.fullPath);
});

// Clear the one-shot reload guard once a navigation actually lands,
// so a later genuine stale-chunk hit can recover again.
router.afterEach((to: RouteLocationNormalized) => {
  sessionStorage.removeItem(`chunk-reload:${to.fullPath}`);
});

export default router;
