<script setup lang="ts">
import Button from "primevue/button";
import { useToast } from "primevue/usetoast";
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppHeader from "@/components/AppHeader.vue";
import { type EventOut, useEventsStore } from "@/stores/events";

const { t, locale } = useI18n();
const events = useEventsStore();
const toast = useToast();

onMounted(async () => {
  try {
    await events.fetchArchived();
  } catch {
    toast.add({ severity: "error", summary: t("archived.loadFailed"), life: 3000 });
  }
});

function localeTag(): string {
  return locale.value === "en" ? "en-GB" : "nl-NL";
}

async function restore(e: EventOut) {
  try {
    await events.restore(e.id);
    toast.add({ severity: "success", summary: t("archived.restored", { name: e.name }), life: 2000 });
  } catch {
    toast.add({ severity: "error", summary: t("archived.restoreFail"), life: 3000 });
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <div class="title-row">
      <h1>{{ t("archived.title") }}</h1>
      <router-link to="/dashboard">
        <Button :label="t('archived.back')" icon="pi pi-arrow-left" size="small" severity="secondary" text />
      </router-link>
    </div>
    <p class="muted">{{ t("archived.intro") }}</p>

    <div v-if="events.archived.length === 0" class="card">
      <p class="muted">{{ t("archived.empty") }}</p>
    </div>

    <div v-for="e in events.archived" :key="e.id" class="card row">
      <div>
        <h3>{{ e.name }}</h3>
        <p class="muted">{{ e.location }} · {{ new Date(e.starts_at).toLocaleString(localeTag()) }}</p>
      </div>
      <Button :label="t('archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restore(e)" />
    </div>
  </div>
</template>

<style scoped>
.title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title-row h1 { margin: 0; }

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.row h3 { margin: 0 0 0.25rem; }
</style>
