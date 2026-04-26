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
      <div class="card stack">
        <h1>{{ event.name }}</h1>
        <p v-if="event.topic" class="muted">{{ event.topic }}</p>
        <p>
          <a
            :href="mapLink({
              location: event.location,
              latitude: event.latitude,
              longitude: event.longitude,
            })"
            target="_blank"
            rel="noopener"
          >
            <strong>{{ event.location }}</strong>
          </a>
          <br />
          {{ new Date(event.starts_at).toLocaleString(localeTag()) }}
        </p>
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
</style>
