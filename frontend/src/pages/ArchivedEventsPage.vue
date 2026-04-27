<script setup lang="ts">
import Button from "primevue/button";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";
import { formatDateTime } from "@/lib/format";
import { useToasts } from "@/lib/toasts";
import { type EventOut, useEventsStore } from "@/stores/events";

const { t, locale } = useI18n();
const events = useEventsStore();
const toasts = useToasts();

const query = ref("");
const loaded = ref(false);

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return events.archived;
  return events.archived.filter(
    (e) => e.name.toLowerCase().includes(q) || e.location.toLowerCase().includes(q),
  );
});

onMounted(async () => {
  try {
    await events.fetchArchived();
  } catch {
    toasts.error(t("archived.loadFailed"));
  } finally {
    loaded.value = true;
  }
});

async function restore(e: EventOut) {
  try {
    await events.restore(e.id);
    toasts.success(t("archived.restored", { name: e.name }));
  } catch {
    toasts.error(t("archived.restoreFail"));
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("archived.title") }}</h1>
    <p class="muted">{{ t("archived.intro") }}</p>

    <SearchInput
      v-if="events.archived.length > 0"
      v-model="query"
      :placeholder="t('archived.searchPlaceholder')"
    />

    <AppSkeleton v-if="!loaded" :rows="2" cards />

    <AppCard v-else-if="events.archived.length === 0" :stack="false">
      <p class="muted">{{ t("archived.empty") }}</p>
    </AppCard>

    <p v-else-if="filtered.length === 0" class="muted">{{ t("archived.noMatches") }}</p>

    <AppCard v-for="e in filtered" :key="e.id" :stack="false" class="row">
      <div>
        <h3>{{ e.name }}</h3>
        <p class="muted">{{ e.location }} · {{ formatDateTime(e.starts_at, locale) }}</p>
      </div>
      <Button :label="t('archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restore(e)" />
    </AppCard>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.row h3 { margin: 0 0 0.25rem; }
</style>
