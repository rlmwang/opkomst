<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import BrandMark from "@/components/BrandMark.vue";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";
import { usePendingCount } from "@/composables/useAdmin";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

// Pending-approval indicator — fired only when the actor is an
// admin (organisers don't get the badge and shouldn't pay the
// network round-trip). The query auto-refetches on the
// staleTime cadence so a new sign-up shows up within ~30s on
// any open admin tab.
const pendingQuery = usePendingCount(computed(() => auth.isAdmin));
const pendingCount = computed(() => pendingQuery.data.value?.count ?? 0);
const showPendingBadge = computed(
  () => auth.isAdmin && pendingCount.value > 0,
);

// Top-level tabs. Each tab knows how to recognise its own
// subtree (so e.g. ``/events/new`` lights up the Evenementen
// tab, not none of them). The Admin tab is a "parent" that
// links to its first subtab.
interface TopTab {
  key: string;
  to: string;
  label: string;
  isActive: (path: string) => boolean;
}
const topTabs = computed<TopTab[]>(() => {
  const tabs: TopTab[] = [
    {
      key: "events",
      to: "/events",
      label: t("header.events"),
      isActive: (p) => p === "/events" || p.startsWith("/events/"),
    },
  ];
  if (auth.isApproved) {
    tabs.push({
      key: "forms",
      to: "/forms",
      label: t("header.forms"),
      isActive: (p) => p === "/forms" || p.startsWith("/forms/"),
    });
    tabs.push({
      key: "datepolls",
      to: "/datepolls",
      label: t("header.datepolls"),
      isActive: (p) => p === "/datepolls" || p.startsWith("/datepolls/"),
    });
  }
  // WhatsApp sits left of Admin, so push it first.
  if (auth.isAdmin && auth.whatsappAvailable) {
    tabs.push({
      key: "whatsapp",
      to: "/admin/whatsapp",
      label: t("header.whatsapp"),
      isActive: (p) => p === "/admin/whatsapp",
    });
  }
  if (auth.isApproved) {
    tabs.push({
      key: "admin",
      to: "/users",
      label: t("header.admin"),
      isActive: (p) => p === "/users" || p === "/chapters",
    });
  }
  return tabs;
});

// Subtabs derived from the current route. Empty array on routes
// that don't sit under one of the parents with subtabs (Lid-
// feedback, WhatsApp, /events/new, /events/:id/edit, /forms/new,
// etc.) — the subtab pair distinguishes only the two list views,
// so hiding it on detail/edit routes keeps the navigation honest.
interface Subtab {
  to: string;
  label: string;
  badge?: number;
}
const subtabs = computed<Subtab[]>(() => {
  const p = route.path;
  if (p === "/events" || p === "/events/archived") {
    return [
      { to: "/events", label: t("header.active") },
      { to: "/events/archived", label: t("header.archive") },
    ];
  }
  if (p === "/forms" || p === "/forms/archived") {
    return [
      { to: "/forms", label: t("header.active") },
      { to: "/forms/archived", label: t("header.archive") },
    ];
  }
  if (p === "/datepolls" || p === "/datepolls/archived") {
    return [
      { to: "/datepolls", label: t("header.active") },
      { to: "/datepolls/archived", label: t("header.archive") },
    ];
  }
  if (p === "/users" || p === "/chapters") {
    return [
      {
        to: "/users",
        label: t("header.users"),
        badge: showPendingBadge.value ? pendingCount.value : undefined,
      },
      { to: "/chapters", label: t("header.chapters") },
    ];
  }
  return [];
});

async function logout() {
  await auth.logout();
  void router.push("/login");
}
</script>

<template>
  <header class="app-header">
    <BrandMark to="/" />
    <div class="header-right">
      <nav v-if="auth.isAuthenticated">
        <!-- Subtabs render to the LEFT of the top tabs with a
             vertical divider. Empty on routes that don't belong
             to either parent's subtree. -->
        <div v-if="subtabs.length" class="nav-group nav-subtabs">
          <router-link
            v-for="s in subtabs"
            :key="s.to"
            :to="s.to"
            class="subtab"
          >
            {{ s.label }}
            <span
              v-if="s.badge"
              class="pending-badge"
              :aria-label="t('header.pendingBadgeLabel', { n: s.badge })"
            >{{ s.badge }}</span>
          </router-link>
          <span class="group-divider" aria-hidden="true" />
        </div>
        <div class="nav-group nav-tabs">
          <router-link
            v-for="tab in topTabs"
            :key="tab.key"
            :to="tab.to"
            :class="['top-tab', { active: tab.isActive(route.path) }]"
          >{{ tab.label }}</router-link>
        </div>
        <span class="logout-divider" aria-hidden="true" />
        <Button :label="t('header.logout')" size="small" severity="secondary" text @click="logout" />
      </nav>
      <LanguageSwitcher />
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* ``flex-wrap: wrap`` is the no-overflow guarantee on narrow
   * viewports — without it, the right-side group (nav links +
   * logout + lang switcher) sticks past the viewport edge and
   * the page picks up horizontal scroll. With wrap the right
   * group drops onto a second row below the brand on phones,
   * unchanged on desktop. */
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid var(--brand-border);
  background: var(--brand-surface);
}
.header-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}
nav {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}
.nav-group {
  display: flex;
  align-items: center;
  gap: 1rem;
}
@media (max-width: 480px) {
  .app-header {
    padding: 0.625rem 0.75rem;
  }
  /* The destructive-action divider eats horizontal space
   * disproportionately on phones; ``gap`` already provides the
   * visual buffer there. */
  .logout-divider {
    display: none;
  }
}
nav a {
  color: var(--brand-text);
  text-decoration: none;
}
/* Top tabs use a manual ``active`` class so the Admin tab can
 * light up for /users and /chapters alike — router-link's own
 * active class only matches the tab's own ``to``. */
.top-tab.active {
  color: var(--brand-red);
  font-weight: 600;
}
/* Subtabs use router-link's built-in active class — each has
 * exactly one matching path. Slightly less prominent than the
 * top-tab active state so the hierarchy reads from left (where
 * the user is right now) to right (the larger menu). */
.subtab.router-link-active {
  color: var(--brand-red);
  font-weight: 500;
}
.subtab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
/* Vertical separator between subtab and top-tab groups, same
 * visual as the logout divider so the bar reads as evenly-
 * partitioned sections. */
.group-divider {
  width: 1px;
  height: 1.5rem;
  background: var(--brand-border);
}
/* Visual + spacing buffer between page navigation and the
 * destructive logout button — easy misclicks were happening when
 * logout sat one nav-gap (1rem) away from the last page link. */
.logout-divider {
  width: 1px;
  height: 1.5rem;
  margin: 0 1rem;
  background: var(--brand-border);
}
/* Brand-red pill carrying the pending-approval count. Sized to
 * fit a 1- or 2-digit number; for ≥10 the pill expands rather
 * than the digits getting clipped. ``min-width`` matches the
 * height so a single-digit count renders as a circle. */
.pending-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  border-radius: 999px;
  background: var(--brand-red);
  color: #ffffff;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
}
</style>
