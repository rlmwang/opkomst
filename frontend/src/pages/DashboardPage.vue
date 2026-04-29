<script setup lang="ts">
import Button from "primevue/button";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";
import { useEventClipboard } from "@/composables/useEventClipboard";
import {
  type EventOut,
  eventList,
  useArchiveEvent,
  useEventList,
} from "@/composables/useEvents";
import { useConfirms } from "@/lib/confirms";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { formatDateTime } from "@/lib/format";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t, locale } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const { copyLink, copyQr } = useEventClipboard();

const eventsQuery = useEventList(computed(() => auth.isApproved));
const events = eventList(eventsQuery);
const archiveMutation = useArchiveEvent();

watch(eventsQuery.isError, (isError) => {
  if (isError) toasts.error(t("dashboard.loadFailed"));
});

const query = ref("");
const loaded = computed(() => !auth.isApproved || !eventsQuery.isPending.value);

const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => b.starts_at.localeCompare(a.starts_at)),
);

const filteredEvents = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return sortedEvents.value;
  return sortedEvents.value.filter(
    (e) => e.name.toLowerCase().includes(q) || e.location.toLowerCase().includes(q),
  );
});

function askArchive(e: EventOut) {
  confirms.ask({
    header: t("dashboard.archiveConfirmTitle"),
    message: t("dashboard.archiveConfirmBody", { name: e.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("dashboard.archive"),
    accept: async () => {
      try {
        await archiveMutation.mutateAsync(e.id);
        toasts.success(t("dashboard.archived"));
      } catch {
        toasts.error(t("dashboard.archiveFail"));
      }
    },
  });
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("dashboard.title") }}</h1>

    <AppCard v-if="!auth.isApproved">
      <h2>{{ t("dashboard.pendingTitle") }}</h2>
      <p>{{ t("dashboard.pendingBody") }}</p>
    </AppCard>

    <template v-else>
      <div class="actions-row">
        <router-link to="/events/new">
          <Button :label="t('dashboard.newEvent')" icon="pi pi-plus" />
        </router-link>
        <SearchInput
          v-if="sortedEvents.length > 0"
          v-model="query"
          :placeholder="t('dashboard.searchPlaceholder')"
          class="search"
        />
      </div>

      <AppSkeleton v-if="!loaded" :rows="3" cards />

      <AppCard v-else-if="sortedEvents.length === 0" :stack="false">
        <p class="muted">{{ t("dashboard.empty") }}</p>
      </AppCard>

      <p v-else-if="filteredEvents.length === 0" class="muted">
        {{ t("dashboard.noMatches") }}
      </p>

      <AppCard v-for="e in filteredEvents" :key="e.id" :stack="false" class="event-card">
        <div class="event-main">
          <div class="event-summary">
            <h3>{{ e.name }}</h3>
            <p class="muted">{{ e.location }} · {{ formatDateTime(e.starts_at, locale) }}</p>
            <div class="link-row">
              <a :href="publicEventUrl(e.slug)" target="_blank" rel="noopener">{{ publicEventUrl(e.slug) }}</a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                :aria-label="t('event.share.copyLink')"
                @click="copyLink(e.slug)"
              />
            </div>
          </div>

          <div class="actions">
            <router-link :to="`/events/${e.id}/details`">
              <Button :label="t('dashboard.details')" icon="pi pi-info-circle" size="small" severity="secondary" />
            </router-link>
            <Button
              :label="t('dashboard.archive')"
              icon="pi pi-archive"
              size="small"
              severity="secondary"
              text
              @click="askArchive(e)"
            />
          </div>
        </div>

        <div class="event-side">
          <div class="muted signup-count">{{ t("dashboard.signupCount", { n: e.signup_count }) }}</div>
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('event.share.copyQr')"
            :aria-label="t('event.share.copyQr')"
            @click="copyQr(e.slug)"
          >
            <img :src="eventQrUrl(e.slug)" alt="" class="qr" />
          </button>
        </div>
      </AppCard>
    </template>
  </div>
</template>

<style scoped>
.actions-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.actions-row .search {
  flex: 1;
  max-width: 24rem;
  margin-left: auto;
}
.event-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.25rem;
  align-items: stretch;
}
.event-main {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  min-width: 0;
}
.event-summary h3 { margin: 0 0 0.25rem; }
.event-summary > .muted { margin: 0; }
.event-summary .link-row { margin-top: 0.25rem; }

.event-side {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  gap: 0.5rem;
}
.signup-count { white-space: nowrap; }

.link-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
}
.link-row a {
  font-size: 0.9375rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.actions {
  display: flex;
  gap: 0.5rem;
  margin-top: auto;
}

.qr-button {
  align-self: center;
  line-height: 0;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  border-radius: 6px;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.qr-button:hover {
  transform: scale(1.03);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 4px;
  display: block;
}

@media (max-width: 540px) {
  .event-card {
    grid-template-columns: 1fr;
  }
  .event-side {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }
}
</style>
