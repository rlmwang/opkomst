<script setup lang="ts">
import { onMounted, ref } from "vue";
import AppHeader from "@/components/AppHeader.vue";
import { type EventOut, type EventStats, useEventsStore } from "@/stores/events";

const props = defineProps<{ eventId: string }>();

const events = useEventsStore();
const event = ref<EventOut | null>(null);
const stats = ref<EventStats | null>(null);

onMounted(async () => {
  // Pull the event details from the cached list. List is loaded on
  // demand if the user landed straight on this URL.
  if (events.all.length === 0) await events.fetchAll();
  event.value = events.all.find((e: EventOut) => e.id === props.eventId) ?? null;
  stats.value = await events.getStats(props.eventId);
});

function publicUrl(slug: string): string {
  return `${window.location.origin}/e/${slug}`;
}

function qrUrl(slug: string): string {
  return `/api/v1/events/by-slug/${slug}/qr.png`;
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <template v-if="event && stats">
      <h1>{{ event.name }}</h1>
      <p class="muted">{{ event.location }} · {{ new Date(event.starts_at).toLocaleString("nl-NL") }}</p>

      <div class="card stack">
        <h2>Aanmeldingen</h2>
        <p><strong>{{ stats.total_signups }}</strong> aanmeldingen, totaal <strong>{{ stats.total_attendees }}</strong> bezoekers.</p>
        <ul v-if="Object.keys(stats.by_source).length > 0">
          <li v-for="(count, src) in stats.by_source" :key="src">
            {{ src }}: {{ count }}
          </li>
        </ul>
      </div>

      <div class="card stack">
        <h2>Deelnamelink &amp; QR</h2>
        <p>
          <a :href="publicUrl(event.slug)" target="_blank" rel="noopener">{{ publicUrl(event.slug) }}</a>
        </p>
        <img :src="qrUrl(event.slug)" alt="QR" class="qr" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.qr {
  width: 200px;
  height: 200px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  padding: 0.5rem;
}
</style>
