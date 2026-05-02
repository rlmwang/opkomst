<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import BrandMark from "@/components/BrandMark.vue";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";
import { usePendingCount } from "@/composables/useAdmin";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const router = useRouter();
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

function logout() {
  auth.logout();
  void router.push("/login");
}
</script>

<template>
  <header class="app-header">
    <BrandMark to="/" />
    <div class="header-right">
      <nav v-if="auth.isAuthenticated">
        <router-link to="/events">{{ t("header.events") }}</router-link>
        <router-link v-if="auth.isApproved" to="/events/archived">{{ t("header.archive") }}</router-link>
        <router-link v-if="auth.isApproved" to="/users" class="users-link">
          {{ t("header.users") }}
          <span
            v-if="showPendingBadge"
            class="pending-badge"
            :aria-label="t('header.pendingBadgeLabel', { n: pendingCount })"
          >{{ pendingCount }}</span>
        </router-link>
        <router-link v-if="auth.isApproved" to="/chapters">{{ t("header.chapters") }}</router-link>
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
nav a.router-link-active {
  color: var(--brand-red);
  font-weight: 600;
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
.users-link {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
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
