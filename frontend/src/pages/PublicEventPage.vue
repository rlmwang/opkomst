<script setup lang="ts">
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import { onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import EventMap from "@/components/EventMap.vue";
import PublicHeader from "@/components/PublicHeader.vue";
import { ApiError } from "@/api/client";
import { formatDate, formatTimeRange } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { type EventOut, useEventsStore } from "@/stores/events";

const props = defineProps<{ slug: string }>();

const { t, locale } = useI18n();
const events = useEventsStore();
const toasts = useToasts();

const event = ref<EventOut | null>(null);
const error = ref<string | null>(null);

const displayName = ref("");
const partySize = ref(1);
const sourceChoice = ref<string | null>(null);
const helpChoices = ref<string[]>([]);
const email = ref("");
const submitting = ref(false);
const submitted = ref(false);

// --- Draft persistence ---------------------------------------------
// The signup form survives a page refresh — important for visitors
// on flaky mobile connections who half-fill the form, lose
// reception, and reload. Keyed by event slug so each event keeps
// its own draft. Cleared when the signup is accepted.
const draftKey = `signup-draft:${props.slug}`;

interface SignupDraft {
  displayName: string;
  partySize: number;
  sourceChoice: string | null;
  helpChoices: string[];
  email: string;
}

function snapshot(): SignupDraft {
  return {
    displayName: displayName.value,
    partySize: partySize.value,
    sourceChoice: sourceChoice.value,
    helpChoices: [...helpChoices.value],
    email: email.value,
  };
}

function applyDraft(d: SignupDraft) {
  displayName.value = d.displayName;
  partySize.value = d.partySize;
  sourceChoice.value = d.sourceChoice;
  helpChoices.value = [...(d.helpChoices ?? [])];
  email.value = d.email;
}

function clearDraft() {
  try {
    localStorage.removeItem(draftKey);
  } catch {
    /* localStorage disabled — nothing to clean up */
  }
}

let _saveTimer: number | null = null;
watch([displayName, partySize, sourceChoice, helpChoices, email], () => {
  if (_saveTimer !== null) clearTimeout(_saveTimer);
  _saveTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(draftKey, JSON.stringify(snapshot()));
    } catch {
      /* localStorage full or disabled — silently skip */
    }
  }, 200);
});

onMounted(async () => {
  try {
    event.value = await events.getBySlug(props.slug);
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 404 ? t("public.notFound") : t("public.loadFailed");
  }
  if (event.value) {
    // Render the public sign-up page in the event's configured
    // language, regardless of the visitor's persisted preference.
    // Set ``locale.value`` directly so localStorage isn't touched
    // (the visitor's own preference shouldn't change just because
    // they followed a link to a foreign-language event).
    locale.value = event.value.locale;
    try {
      const raw = localStorage.getItem(draftKey);
      if (raw) applyDraft(JSON.parse(raw) as SignupDraft);
    } catch {
      /* unparseable draft — ignore */
    }
  }
});

async function submit() {
  if (!event.value) return;
  const name = displayName.value.trim();
  const trimmedEmail = email.value.trim();
  if (trimmedEmail && !isValidEmail(trimmedEmail)) {
    toasts.warn(t("common.invalidEmail"));
    return;
  }
  submitting.value = true;
  try {
    await events.signUp(props.slug, {
      display_name: name || null,
      party_size: partySize.value,
      source_choice: sourceChoice.value,
      help_choices: helpChoices.value,
      email: trimmedEmail || null,
    });
    submitted.value = true;
    clearDraft();
  } catch {
    // Public visitors should never see a raw backend message — keep
    // the toast localised, regardless of the underlying status.
    toasts.error(t("public.submitFail"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="container stack">
    <PublicHeader />

    <AppCard v-if="error" :stack="false">
      <p>{{ error }}</p>
    </AppCard>

    <template v-else-if="event">
      <AppCard :stack="false" class="event-header">
        <div class="event-title">
          <h1>{{ event.name }}</h1>
          <p v-if="event.topic" class="event-topic">{{ event.topic }}</p>
        </div>

        <dl class="event-meta">
          <div class="meta-row">
            <i class="pi pi-calendar" aria-hidden="true" />
            <span>{{ formatDate(event.starts_at, locale) }}</span>
          </div>
          <div class="meta-row">
            <i class="pi pi-clock" aria-hidden="true" />
            <span>{{ formatTimeRange(event.starts_at, event.ends_at, locale) }}</span>
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
      </AppCard>

      <AppCard v-if="!submitted" :stack="false" class="privacy-card">
        <details>
          <summary>{{ t("public.explainerTitle") }}</summary>
          <p class="privacy-body">
            {{ event.questionnaire_enabled ? t("public.explainerBody") : t("public.explainerBodyNoEmail") }}
            <a href="https://github.com/rlmwang/opkomst" target="_blank" rel="noopener">{{ t("public.explainerLink") }}</a>.
          </p>
        </details>
      </AppCard>

      <AppCard v-if="submitted">
        <h2>{{ t("public.thanks") }}</h2>
        <p class="muted">
          {{ event.questionnaire_enabled ? t("public.thanksBody") : t("public.thanksBodyNoEmail") }}
        </p>
      </AppCard>

      <AppCard v-else tag="form" class="signup-form" novalidate @submit.prevent="submit">
        <h2>{{ t("public.essentialsTitle") }}</h2>

        <section class="form-section">
          <InputText v-model="displayName" :placeholder="t('public.displayName')" fluid />
          <InputNumber v-model="partySize" :min="1" :max="50" :placeholder="t('public.partySize')" show-buttons fluid />
        </section>

        <section v-if="event.help_options.length > 0" class="form-section help-section">
          <fieldset class="help-choices">
            <legend>{{ t("public.helpHeading") }}</legend>
            <label v-for="opt in event.help_options" :key="opt" class="help-row">
              <Checkbox v-model="helpChoices" :value="opt" />
              <span>{{ opt }}</span>
            </label>
          </fieldset>
        </section>

        <hr class="section-divider" />

        <h2>{{ t("public.feedbackTitle") }}</h2>

        <section class="form-section">
          <Select
            v-model="sourceChoice"
            :options="event.source_options"
            :placeholder="t('public.sourcePlaceholder')"
            fluid
          />
          <InputText
            v-if="event.questionnaire_enabled"
            v-model="email"
            type="email"
            :placeholder="t('public.emailOptional')"
            autocomplete="email"
            fluid
          />
        </section>

        <div class="submit-row">
          <Button type="submit" :label="t('public.submit')" :loading="submitting" />
        </div>
      </AppCard>

    </template>
  </div>
</template>

<style scoped>
/* Each labelled block on the public sign-up form is a
 * ``form-section``; inside the section, fields stack at the
 * standard 0.75rem; between sections we open up 2rem so a
 * mobile-first form doesn't feel like one dense column. */
.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.form-section + .form-section {
  margin-top: 2rem;
}
/* Slightly tighter break above the help-with checkboxes — the
 * fieldset's own legend already adds visual weight, no need for
 * the full inter-section margin on top of it. */
.help-section {
  margin-top: 1.25rem !important;
}
/* Calm horizontal separator between the two halves of the form.
 * Subtle border with symmetric breathing room above and below. */
.section-divider {
  border: 0;
  border-top: 1px solid var(--brand-rule, rgba(0, 0, 0, 0.08));
  margin: 1.5rem 0;
}
/* Second h2 (Help ons leren / Help us learn) follows the divider —
 * suppress the .stack 0.75rem so the divider's symmetric margins
 * own the spacing. */
.signup-form > .section-divider + h2 {
  margin-top: 0;
}
/* Card heading sits clearly above the first field. AppCard renders
 * as ``<form class="signup-form card stack">`` so the h2 is a
 * direct child of ``.signup-form`` — no ``:deep(.card)`` indirection
 * (that was the bug behind the spacing requests not landing). */
.signup-form > h2 {
  margin-bottom: 1.5rem;
}
/* Privacy explainer between the event header and the sign-up form.
 * A normal-looking card, but the contents are a foldable
 * ``<details>`` so the section is one click away rather than
 * always-on; closed by default so it doesn't dominate the page. */
.privacy-card summary {
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  padding: 0.125rem 0;
}
.privacy-card .privacy-body {
  margin: 0.75rem 0 0;
  font-size: 0.9375rem;
  color: var(--brand-text-muted);
  line-height: 1.5;
}
/* Bottom row of the card: submit button right-aligned. */
.submit-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 2rem;
}
/* "I can help with" — multi-select rendered as a vertical stack of
 * checkboxes. Fieldset reset because PrimeVue doesn't ship a
 * checkbox group component that styles legends consistently. */
.help-choices {
  border: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.help-choices legend {
  padding: 0;
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
}
.help-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  cursor: pointer;
  font-size: 0.95rem;
}

.event-header {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.event-title h1 {
  margin: 0;
  font-size: 1.5rem;
  line-height: 1.25;
}
.event-topic {
  margin: 0.75rem 0 0;
  padding: 0.25rem 0;
  color: var(--brand-text-muted);
  font-style: italic;
  font-size: 1.0625rem;
  line-height: 1.5;
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
/* External-link affix shown next to a meta-link's text. Stays
 * scoped because it's only used on this page's location row. */
.meta-link .external {
  font-size: 0.7rem;
  color: var(--brand-text-muted);
  margin-left: 0.3rem;
}
</style>
