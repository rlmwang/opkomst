<script setup lang="ts">
import Button from "primevue/button";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppHeader from "@/components/AppHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { type EventOut, useEventsStore } from "@/stores/events";

const { t, locale } = useI18n();
const auth = useAuthStore();
const events = useEventsStore();
const toast = useToast();
const confirm = useConfirm();

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

function qrUrl(slug: string): string {
  return `/api/v1/events/by-slug/${slug}/qr.png`;
}

async function copyLink(slug: string) {
  try {
    await navigator.clipboard.writeText(publicUrl(slug));
    toast.add({ severity: "success", summary: t("dashboard.linkCopied"), life: 1800 });
  } catch {
    /* clipboard API can be unavailable on http without permission; silently no-op */
  }
}

function askArchive(e: EventOut) {
  confirm.require({
    message: t("dashboard.archiveConfirmBody", { name: e.name }),
    header: t("dashboard.archiveConfirmTitle"),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("dashboard.archive"),
    acceptProps: { severity: "danger" },
    accept: async () => {
      try {
        await events.archive(e.id);
        toast.add({ severity: "success", summary: t("dashboard.archived"), life: 2000 });
      } catch {
        toast.add({ severity: "error", summary: t("dashboard.archiveFail"), life: 3000 });
      }
    },
  });
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <div class="title-row">
      <h1>{{ t("dashboard.title") }}</h1>
      <router-link v-if="auth.isApproved" to="/events/archived">
        <Button :label="t('dashboard.viewArchived')" icon="pi pi-archive" size="small" severity="secondary" text />
      </router-link>
    </div>

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

      <div v-for="e in sortedEvents" :key="e.id" class="card event-card">
        <div class="event-main">
          <div class="event-header">
            <div>
              <h3>{{ e.name }}</h3>
              <p class="muted">{{ e.location }} · {{ new Date(e.starts_at).toLocaleString(localeTag()) }}</p>
            </div>
            <div class="muted signup-count">{{ t("dashboard.signupCount", { n: e.signup_count }) }}</div>
          </div>

          <div class="link-row">
            <a :href="publicUrl(e.slug)" target="_blank" rel="noopener">{{ publicUrl(e.slug) }}</a>
            <Button
              icon="pi pi-copy"
              size="small"
              severity="secondary"
              text
              :aria-label="t('dashboard.copyLink')"
              v-tooltip.top="t('dashboard.copyLink')"
              @click="copyLink(e.slug)"
            />
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

        <a :href="publicUrl(e.slug)" target="_blank" rel="noopener" class="qr-link">
          <img :src="qrUrl(e.slug)" alt="QR" class="qr" />
        </a>
      </div>
    </template>
  </div>
</template>

<style scoped>
.title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title-row h1 { margin: 0; }

.event-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.25rem;
  align-items: stretch;
}
.event-main {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  min-width: 0;
}
.event-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.event-header h3 { margin: 0 0 0.25rem; }
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

.qr-link {
  align-self: center;
  line-height: 0;
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
  .qr-link {
    align-self: flex-start;
  }
}
</style>
