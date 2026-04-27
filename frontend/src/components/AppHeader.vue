<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import BrandMark from "@/components/BrandMark.vue";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();

function logout() {
  auth.logout();
  void router.push("/login");
}
</script>

<template>
  <header class="app-header">
    <BrandMark to="/" />
    <nav v-if="auth.isAuthenticated">
      <router-link to="/dashboard">{{ t("header.events") }}</router-link>
      <router-link v-if="auth.isApproved" to="/events/archived">{{ t("header.archive") }}</router-link>
      <router-link v-if="auth.isAdmin" to="/admin">{{ t("header.admin") }}</router-link>
      <span class="logout-divider" aria-hidden="true" />
      <Button :label="t('header.logout')" size="small" severity="secondary" text @click="logout" />
    </nav>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid var(--brand-border);
  background: var(--brand-surface);
}
nav {
  display: flex;
  align-items: center;
  gap: 1rem;
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
</style>
