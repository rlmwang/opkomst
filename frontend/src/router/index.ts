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
  // ``/e/:slug`` is no longer in the admin SPA router — it's
  // served by the backend as a separate Vue mini-app
  // (``frontend/public-event.html`` + ``src/public/``) with the
  // event payload inlined into the HTML response. See
  // ``backend/routers/spa.py``. Only the feedback flow is left in
  // the admin bundle because it's a one-off form gated on a
  // single-use token, low traffic.
  { path: "/e/:slug/feedback", component: () => import("@/pages/FeedbackPage.vue"), props: true },
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
  return true;
});

export default router;
