<script setup lang="ts">
import Button from "primevue/button";
import { useToast } from "primevue/usetoast";
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppHeader from "@/components/AppHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";

const { t, locale } = useI18n();
const auth = useAuthStore();
const events = useEventsStore();
const toast = useToast();

async function resend() {
  try {
    await auth.resendVerification();
    toast.add({ severity: "success", summary: t("verify.resentOk"), life: 3000 });
  } catch {
    toast.add({ severity: "error", summary: t("verify.resentFail"), life: 3000 });
  }
}

const sortedEvents = computed(() =>
  [...events.all].sort((a, b) => b.starts_at.localeCompare(a.starts_at)),
);

onMounted(async () => {
  if (!auth.isApproved) return;
  try {
    await events.fetchAll();
  } catch {
    toast.add({ severity: "error", summary: t("dashboard.loadFailed"), life: 3000 });
  }
});

function localeTag(): string {
  return locale.value === "en" ? "en-GB" : "nl-NL";
}

function publicUrl(slug: string): string {
  return `${window.location.origin}/e/${slug}`;
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("dashboard.title") }}</h1>

    <div v-if="!auth.isVerified" class="card stack">
      <h2>{{ t("dashboard.unverifiedTitle") }}</h2>
      <p>{{ t("dashboard.unverifiedBody") }}</p>
      <div>
        <Button :label="t('verify.resend')" size="small" severity="secondary" @click="resend" />
      </div>
    </div>

    <div v-else-if="!auth.isApproved" class="card stack">
      <h2>{{ t("dashboard.pendingTitle") }}</h2>
      <p>{{ t("dashboard.pendingBody") }}</p>
    </div>

    <template v-else>
      <div>
        <router-link to="/events/new">
          <Button :label="t('dashboard.newEvent')" icon="pi pi-plus" />
        </router-link>
      </div>

      <div v-if="sortedEvents.length === 0" class="card">
        <p class="muted">{{ t("dashboard.empty") }}</p>
      </div>

      <div v-for="e in sortedEvents" :key="e.id" class="card stack">
        <div class="event-row">
          <div>
            <h3>{{ e.name }}</h3>
            <p class="muted">{{ e.location }} · {{ new Date(e.starts_at).toLocaleString(localeTag()) }}</p>
          </div>
          <div class="muted">{{ t("dashboard.signupCount", { n: e.signup_count }) }}</div>
        </div>
        <div class="event-actions">
          <a :href="publicUrl(e.slug)" target="_blank" rel="noopener">{{ publicUrl(e.slug) }}</a>
          <router-link :to="`/events/${e.id}/stats`">
            <Button :label="t('dashboard.stats')" size="small" severity="secondary" text />
          </router-link>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.event-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.event-row h3 { margin: 0 0 0.25rem; }
.event-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
</style>
