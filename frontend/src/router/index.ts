import { createRouter, createWebHistory, type RouteLocationNormalized } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes = [
  { path: "/", redirect: "/events" },
  { path: "/login", component: () => import("@/pages/LoginPage.vue") },
  { path: "/register/complete", component: () => import("@/pages/RegisterCompletePage.vue") },
  { path: "/auth/redeem", component: () => import("@/pages/RedeemPage.vue") },
  { path: "/events", component: () => import("@/pages/DashboardPage.vue"), meta: { requiresAuth: true } },
  { path: "/users", component: () => import("@/pages/UsersPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/chapters", component: () => import("@/pages/ChaptersPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/new", component: () => import("@/pages/EventFormPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/:eventId/edit", component: () => import("@/pages/EventFormPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/:eventId/details", component: () => import("@/pages/EventDetailsPage.vue"), props: true, meta: { requiresAuth: true } },
  { path: "/events/archived", component: () => import("@/pages/ArchivedEventsPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  // Forms — standalone questionnaires (no relation to Events).
  // Same chapter-scoped four-page experience: active list /
  // archived list / details / edit. The public fill-out lives
  // at /f/:slug and is unauthenticated.
  { path: "/forms", component: () => import("@/pages/FormListPage.vue"), meta: { requiresAuth: true } },
  { path: "/forms/archived", component: () => import("@/pages/ArchivedFormsPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/forms/new", component: () => import("@/pages/FormEditPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/forms/:formId/edit", component: () => import("@/pages/FormEditPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/forms/:formId/details", component: () => import("@/pages/FormDetailsPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  // Datepolls — dates-only availability polls (no relation to
  // Events/Forms). Same chapter-scoped four-page experience; the
  // public fill-out lives at /d/:slug and is unauthenticated
  // (served by the backend mini-app, not this router).
  { path: "/datepolls", component: () => import("@/pages/DatepollListPage.vue"), meta: { requiresAuth: true } },
  { path: "/datepolls/archived", component: () => import("@/pages/ArchivedDatepollsPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/datepolls/new", component: () => import("@/pages/DatepollEditPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/datepolls/:datepollId/edit", component: () => import("@/pages/DatepollEditPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/datepolls/:datepollId/details", component: () => import("@/pages/DatepollDetailsPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
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
  { path: "/admin/whatsapp", component: () => import("@/pages/AdminWhatsAppPage.vue"), meta: { requiresAuth: true, requiresAdmin: true, requiresWhatsApp: true } },
  { path: "/:pathMatch(.*)*", component: () => import("@/pages/NotFoundPage.vue") },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to: RouteLocationNormalized) => {
  const auth = useAuthStore();
  // Only routes that gate on auth state need to know whether the
  // visitor is logged in. Public routes (``/e/:slug``,
  // ``/e/:slug/feedback``, ``/login``, ``/register/complete``) skip the
  // ``auth/me`` round-trip entirely — visitors don't have a JWT
  // and shouldn't pay a network hop to confirm that.
  const needsAuth =
    to.meta.requiresAuth || to.meta.requiresAdmin || to.meta.requiresApproved;
  if (needsAuth && !auth.loaded) await auth.fetchMe();

  if (to.meta.requiresAuth && !auth.isAuthenticated) return { path: "/login", query: { next: to.fullPath } };
  if (to.meta.requiresAdmin && !auth.isAdmin) return { path: "/events" };
  if (to.meta.requiresApproved && !auth.isApproved) return { path: "/events" };
  if (to.meta.requiresWhatsApp && !auth.whatsappAvailable) return { path: "/events" };
  return true;
});

export default router;
