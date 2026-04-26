<script setup lang="ts">
import Button from "primevue/button";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();

function logout() {
  auth.logout();
  void router.push("/login");
}
</script>

<template>
  <header class="app-header">
    <router-link to="/" class="brand">opkomst</router-link>
    <nav v-if="auth.isAuthenticated">
      <router-link to="/dashboard">Evenementen</router-link>
      <router-link v-if="auth.isAdmin" to="/admin">Admin</router-link>
      <Button label="Uitloggen" size="small" severity="secondary" text @click="logout" />
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
.brand {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--brand-red);
  text-decoration: none;
  letter-spacing: 0.5px;
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
</style>
