import type { RouteDef } from "./router.svelte";

/**
 * Every page in the organiser app, in one flat table.
 *
 * Each one is a lazy import, so a page's code arrives when somebody goes
 * to it and not before. The meta on a route is what the guard reads
 * (``navigation.svelte.ts``); the ordering matters only for the
 * catch-all, which has to come last.
 */
export const routes: RouteDef[] = [
  // ``/{tenant}``: the organiser's landing page when signed in, the
  // organisation's public chapter index when not. Deliberately not
  // ``requiresAuth``: a visitor with no session gets the public face,
  // which is also where the sign-in form lives.
  { path: "/", load: () => import("@/pages/HomePage.svelte") },
  { path: "/register/complete", load: () => import("@/pages/RegisterCompletePage.svelte") },
  { path: "/auth/redeem", load: () => import("@/pages/RedeemPage.svelte") },

  // Every workspace needs an approved account. One still waiting on an
  // admin has nothing to do in any of them, and being shown six doors
  // that all open onto "you are not approved yet" is worse than being
  // told once, on the landing page.
  {
    path: "/event",
    load: () => import("@/pages/DashboardPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },

  // ``requiresOrganisation``: these act on an organisation's people and
  // its chapters, and a personal account has neither. The API refuses
  // them for such an account; the guard keeps a typed URL from getting
  // there and finding a page full of errors.
  {
    path: "/users",
    load: () => import("@/pages/UsersPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true, requiresOrganisation: true },
  },
  {
    path: "/chapters",
    load: () => import("@/pages/ChaptersPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true, requiresOrganisation: true },
  },
  {
    path: "/settings",
    load: () => import("@/pages/SettingsPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true, requiresOrganisation: true },
  },

  // ``startable``: at the root a create form is also the signed-out
  // front door. A tile on the landing page opens the form itself, and
  // the address is a field in it rather than a wall in front of it.
  // Under an organisation's slug the flag does nothing, because there
  // the visitor is somebody's organiser or nobody.
  {
    path: "/event/new",
    load: () => import("@/pages/EventFormPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true, startable: true },
  },
  {
    path: "/event/:eventId/edit",
    load: () => import("@/pages/EventFormPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/event/:eventId/details",
    load: () => import("@/pages/EventDetailsPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/event/archived",
    load: () => import("@/pages/ArchivedEventsPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },

  // The forms table's three products are the same four pages,
  // registered once each and told apart by ``meta.resource``, which is
  // what the pages read to decide which API they are on. A quiz differs
  // from a questionnaire by an answer key and a score, a kompas by a
  // direction on every answer and a map at the end, and none of that is
  // on this side of the app.
  ...(["form", "quiz", "compass"] as const).flatMap((resource): RouteDef[] => [
    {
      path: `/${resource}`,
      load: () => import("@/pages/FormListPage.svelte"),
      meta: { requiresAuth: true, requiresApproved: true, resource },
    },
    {
      path: `/${resource}/archived`,
      load: () => import("@/pages/ArchivedFormsPage.svelte"),
      meta: { requiresAuth: true, requiresApproved: true, resource },
    },
    {
      path: `/${resource}/new`,
      load: () => import("@/pages/FormEditPage.svelte"),
      meta: { requiresAuth: true, requiresApproved: true, startable: true, resource },
    },
    {
      path: `/${resource}/:formId/edit`,
      load: () => import("@/pages/FormEditPage.svelte"),
      meta: { requiresAuth: true, requiresApproved: true, resource },
    },
    {
      path: `/${resource}/:formId/details`,
      load: () => import("@/pages/FormDetailsPage.svelte"),
      meta: { requiresAuth: true, requiresApproved: true, resource },
    },
  ]),

  // Date polls. The public one lives at ``/d/{slug}`` and is its own
  // mini-app, not a route here.
  {
    path: "/datepoll",
    load: () => import("@/pages/DatepollListPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/datepoll/archived",
    load: () => import("@/pages/ArchivedDatepollsPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/datepoll/new",
    load: () => import("@/pages/DatepollEditPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true, startable: true },
  },
  {
    path: "/datepoll/:datepollId/edit",
    load: () => import("@/pages/DatepollEditPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/datepoll/:datepollId/details",
    load: () => import("@/pages/DatepollDetailsPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },

  // Rosters. The public enrol page at ``/c/{slug}`` is its own mini-app
  // too.
  {
    path: "/chore",
    load: () => import("@/pages/ChoresListPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/chore/archived",
    load: () => import("@/pages/ArchivedChoresPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/chore/new",
    load: () => import("@/pages/ChoresEditPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true, startable: true },
  },
  {
    path: "/chore/:rosterId/edit",
    load: () => import("@/pages/ChoresEditPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },
  {
    path: "/chore/:rosterId/details",
    load: () => import("@/pages/ChoresDetailsPage.svelte"),
    meta: { requiresAuth: true, requiresApproved: true },
  },

  // The one public page left in this bundle. The sign-up page itself is
  // a mini-app; this is a one-off form behind a single-use token, and
  // low enough traffic not to be worth its own entry.
  { path: "/e/:slug/feedback", load: () => import("@/pages/FeedbackPage.svelte") },

  // ``requiresWhatsApp`` sends a typed URL back to the events list when
  // the server has no WhatsApp configured, rather than opening a page
  // that cannot work.
  {
    path: "/admin/whatsapp",
    load: () => import("@/pages/AdminWhatsAppPage.svelte"),
    meta: {
      requiresAuth: true,
      requiresAdmin: true,
      requiresWhatsApp: true,
      requiresOrganisation: true,
    },
  },

  { path: "/*", load: () => import("@/pages/NotFoundPage.svelte") },
];
