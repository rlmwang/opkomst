<script setup lang="ts">
import Button from "primevue/button";
import { useToast } from "primevue/usetoast";
import { computed, onMounted } from "vue";
import AppHeader from "@/components/AppHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";

const auth = useAuthStore();
const events = useEventsStore();
const toast = useToast();

const sortedEvents = computed(() =>
  [...events.mine].sort((a, b) => b.starts_at.localeCompare(a.starts_at)),
);

onMounted(async () => {
  if (!auth.isApproved) return;
  try {
    await events.fetchMine();
  } catch {
    toast.add({ severity: "error", summary: "Kon evenementen niet laden", life: 3000 });
  }
});

function publicUrl(slug: string): string {
  return `${window.location.origin}/e/${slug}`;
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>Evenementen</h1>

    <div v-if="!auth.isApproved" class="card stack">
      <h2>Account in afwachting</h2>
      <p>
        Je account is aangemaakt, maar moet nog door een admin worden goedgekeurd
        voordat je evenementen kunt aanmaken. Neem contact op met een bestaande
        admin als dat nog even duurt.
      </p>
    </div>

    <template v-else>
      <div>
        <router-link to="/events/new">
          <Button label="Nieuw evenement" icon="pi pi-plus" />
        </router-link>
      </div>

      <div v-if="sortedEvents.length === 0" class="card">
        <p class="muted">Nog geen evenementen aangemaakt.</p>
      </div>

      <div v-for="e in sortedEvents" :key="e.id" class="card stack">
        <div class="event-row">
          <div>
            <h3>{{ e.name }}</h3>
            <p class="muted">{{ e.location }} · {{ new Date(e.starts_at).toLocaleString("nl-NL") }}</p>
          </div>
          <div class="muted">{{ e.signup_count }} aanmeldingen</div>
        </div>
        <div class="event-actions">
          <a :href="publicUrl(e.slug)" target="_blank" rel="noopener">{{ publicUrl(e.slug) }}</a>
          <router-link :to="`/events/${e.id}/stats`">
            <Button label="Statistieken" size="small" severity="secondary" text />
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
