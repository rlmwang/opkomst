<script setup lang="ts">
import Button from "primevue/button";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";
import {
  type EventOut,
  useArchivedEvents,
  useRestoreEvent,
} from "@/composables/useEvents";
import { formatDateTime } from "@/lib/format";
import { useToasts } from "@/lib/toasts";

const { t, locale } = useI18n();
const toasts = useToasts();

const archivedQuery = useArchivedEvents();
const archived = computed<EventOut[]>(() => archivedQuery.data.value ?? []);
const restoreMutation = useRestoreEvent();

watch(archivedQuery.isError, (isError) => {
  if (isError) toasts.error(t("archived.loadFailed"));
});

const query = ref("");
const loaded = computed(() => !archivedQuery.isPending.value);

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return archived.value;
  return archived.value.filter(
    (e) => e.name.toLowerCase().includes(q) || e.location.toLowerCase().includes(q),
  );
});

async function restore(e: EventOut) {
  try {
    await restoreMutation.mutateAsync(e.id);
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
      v-if="archived.length > 0"
      v-model="query"
      :placeholder="t('archived.searchPlaceholder')"
    />

    <AppSkeleton v-if="!loaded" :rows="2" cards />

    <AppCard v-else-if="archived.length === 0" :stack="false">
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
