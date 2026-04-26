<script setup lang="ts">
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import { useToast } from "primevue/usetoast";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import EventMap from "@/components/EventMap.vue";
import { ApiError } from "@/api/client";
import { type EventOut, useEventsStore } from "@/stores/events";
import { mapLink } from "@/lib/map-link";

const props = defineProps<{ slug: string }>();

const { t, locale } = useI18n();
const events = useEventsStore();
const toast = useToast();

function localeTag(): string {
  return locale.value === "en" ? "en-GB" : "nl-NL";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(localeTag(), {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatTimeRange(startIso: string, endIso: string): string {
  const opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };
  const start = new Date(startIso).toLocaleTimeString(localeTag(), opts);
  const end = new Date(endIso).toLocaleTimeString(localeTag(), opts);
  return `${start} — ${end}`;
}

const event = ref<EventOut | null>(null);
const error = ref<string | null>(null);

const displayName = ref("");
const partySize = ref(1);
const sourceChoice = ref<string | null>(null);
const email = ref("");
const submitting = ref(false);
const submitted = ref(false);

onMounted(async () => {
  try {
    event.value = await events.getBySlug(props.slug);
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 404 ? t("public.notFound") : t("public.loadFailed");
  }
});

async function submit() {
  if (!event.value || !sourceChoice.value) return;
  submitting.value = true;
  try {
    await events.signUp(props.slug, {
      display_name: displayName.value,
      party_size: partySize.value,
      source_choice: sourceChoice.value,
      email: email.value.trim() ? email.value.trim() : null,
    });
    submitted.value = true;
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : t("public.submitFail");
    toast.add({ severity: "error", summary: msg, life: 3000 });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="container stack">
    <header class="public-header">
      <span class="brand">opkomst</span>
    </header>

    <div v-if="error" class="card">
      <p>{{ error }}</p>
    </div>

    <template v-else-if="event">
      <div class="card event-header">
        <div class="event-title">
          <h1>{{ event.name }}</h1>
          <p v-if="event.topic" class="event-topic">{{ event.topic }}</p>
        </div>

        <dl class="event-meta">
          <div class="meta-row">
            <i class="pi pi-calendar" aria-hidden="true" />
            <span>{{ formatDate(event.starts_at) }}</span>
          </div>
          <div class="meta-row">
            <i class="pi pi-clock" aria-hidden="true" />
            <span>{{ formatTimeRange(event.starts_at, event.ends_at) }}</span>
          </div>
          <div class="meta-row">
            <i class="pi pi-map-marker" aria-hidden="true" />
            <a
              :href="mapLink({
                location: event.location,
                latitude: event.latitude,
                longitude: event.longitude,
              })"
              target="_blank"
              rel="noopener"
              class="meta-link"
            >
              {{ event.location }}
              <i class="pi pi-external-link external" aria-hidden="true" />
            </a>
          </div>
        </dl>

        <EventMap
          v-if="event.latitude !== null && event.longitude !== null"
          :latitude="event.latitude"
          :longitude="event.longitude"
        />
      </div>

      <div v-if="submitted" class="card stack">
        <h2>{{ t("public.thanks") }}</h2>
        <p class="muted">{{ t("public.thanksBody") }}</p>
      </div>

      <form v-else class="card stack" @submit.prevent="submit">
        <h2>{{ t("public.signup") }}</h2>
        <details class="privacy-notice">
          <summary>{{ t("public.explainerTitle") }}</summary>
          <p>
            {{ t("public.explainerBody") }}
            <a href="https://github.com/rlmwang/opkomst" target="_blank" rel="noopener">{{ t("public.explainerLink") }}</a>.
          </p>
        </details>
        <InputText v-model="displayName" :placeholder="t('public.displayName')" required fluid />
        <div class="field-with-help">
          <InputNumber v-model="partySize" :min="1" :max="50" :placeholder="t('public.partySize')" show-buttons fluid />
          <p class="field-help">{{ t("public.partySizeHelp") }}</p>
        </div>
        <Select
          v-model="sourceChoice"
          :options="event.source_options"
          :placeholder="t('public.sourcePlaceholder')"
          required
          fluid
        />
        <InputText v-model="email" type="email" :placeholder="t('public.emailOptional')" autocomplete="email" fluid />
        <Button type="submit" :label="t('public.submit')" :loading="submitting" />
      </form>
    </template>
  </div>
</template>

<style scoped>
.public-header {
  padding: 1rem 0;
}
.brand {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--brand-red);
  letter-spacing: 0.5px;
}
.field-with-help {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field-help {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}

.event-header {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.event-title h1 {
  margin: 0;
  line-height: 1.2;
}
.event-topic {
  margin: 0.25rem 0 0;
  color: var(--brand-text-muted);
  font-style: italic;
  font-size: 0.95rem;
}
.event-meta {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.95rem;
  line-height: 1.3;
}
.meta-row > i {
  color: var(--brand-red);
  font-size: 1rem;
  width: 1rem;
  text-align: center;
  flex-shrink: 0;
}
.meta-link {
  color: var(--brand-text);
  text-decoration: none;
  border-bottom: 1px dotted var(--brand-border);
  padding-bottom: 1px;
  transition: color 120ms ease, border-color 120ms ease;
}
.meta-link:hover {
  color: var(--brand-red);
  border-bottom-color: var(--brand-red);
}
.meta-link .external {
  font-size: 0.7rem;
  color: var(--brand-text-muted);
  margin-left: 0.3rem;
}
</style>
