import { createRouter, createWebHistory, type RouteLocationNormalized } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes = [
  { path: "/", redirect: "/dashboard" },
  { path: "/login", component: () => import("@/pages/LoginPage.vue") },
  { path: "/register", component: () => import("@/pages/RegisterPage.vue") },
  { path: "/dashboard", component: () => import("@/pages/DashboardPage.vue"), meta: { requiresAuth: true } },
  { path: "/admin", component: () => import("@/pages/AdminPage.vue"), meta: { requiresAuth: true, requiresAdmin: true } },
  { path: "/events/new", component: () => import("@/pages/EventFormPage.vue"), meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/:eventId/edit", component: () => import("@/pages/EventFormPage.vue"), props: true, meta: { requiresAuth: true, requiresApproved: true } },
  { path: "/events/:eventId/stats", component: () => import("@/pages/EventStatsPage.vue"), props: true, meta: { requiresAuth: true } },
  { path: "/e/:slug", component: () => import("@/pages/PublicEventPage.vue"), props: true },
  { path: "/:pathMatch(.*)*", component: () => import("@/pages/NotFoundPage.vue") },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to: RouteLocationNormalized) => {
  const auth = useAuthStore();
  if (!auth.loaded) await auth.fetchMe();

  if (to.meta.requiresAuth && !auth.isAuthenticated) return { path: "/login", query: { next: to.fullPath } };
  if (to.meta.requiresAdmin && !auth.isAdmin) return { path: "/dashboard" };
  if (to.meta.requiresApproved && !auth.isApproved) return { path: "/dashboard" };
  return true;
});

export default router;
