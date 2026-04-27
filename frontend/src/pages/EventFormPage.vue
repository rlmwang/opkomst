<script setup lang="ts">
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import EditableList from "@/components/EditableList.vue";
import LocationPicker from "@/components/LocationPicker.vue";
import { useToasts } from "@/lib/toasts";
import { useChaptersStore } from "@/stores/chapters";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";

const props = defineProps<{ eventId?: string }>();

const { t, locale } = useI18n();
const router = useRouter();
const events = useEventsStore();
const toasts = useToasts();
const chapters = useChaptersStore();
const auth = useAuthStore();

const isEdit = computed(() => Boolean(props.eventId));

// Bias address suggestions toward the organiser's chapter's home
// city. Resolved from the chapters store rather than the cached
// auth.user copy so a chapter that gets a city assigned mid-session
// flows through without a re-login.
const chapterBias = computed<{ lat: number | null; lon: number | null }>(() => {
  const id = auth.user?.chapter_id;
  if (!id) return { lat: null, lon: null };
  const a = chapters.all.find((x) => x.id === id);
  return { lat: a?.city_lat ?? null, lon: a?.city_lon ?? null };
});

const name = ref("");
const topic = ref("");
const location = ref("");
const latitude = ref<number | null>(null);
const longitude = ref<number | null>(null);
const eventDate = ref<Date | null>(null);
// Most events run in the evening — pre-fill 20:00 / 22:00 so the
// organiser only has to pick the date and tweak if needed. The date
// portion is irrelevant (``combine()`` merges the picked date with
// these times before save). Edit-mode and the draft restore both
// overwrite these defaults below.
const startTime = ref<Date | null>(_timeAt(20));
const endTime = ref<Date | null>(_timeAt(22));
// Default ``How did you find us?`` options, ordered by typical
// frequency for grassroots events (word of mouth dominates, posters
// are the long tail) and seeded in the organiser's current locale.
// Stored as plain strings on the event — once saved they don't
// auto-translate, but the organiser can rename or remove any of them
// before saving.
const sources = ref<string[]>([
  t("event.sourceDefaults.wordOfMouth"),
  t("event.sourceDefaults.socialMedia"),
  t("event.sourceDefaults.flyer"),
  t("event.sourceDefaults.poster"),
]);
const newSource = ref("");
// Default "I can help with" tasks. Optional — leave empty to hide
// the question on the public form. Seeded in the organiser's locale;
// once saved the strings are static (no auto-translate).
const helpOptions = ref<string[]>([
  t("event.helpDefaults.setup"),
  t("event.helpDefaults.teardown"),
]);
const newHelp = ref("");
const questionnaireEnabled = ref(true);
// Default to the organiser's UI locale — they can override per-event
// (e.g. an English-language event in NL).
const eventLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
const submitting = ref(false);

// --- Draft persistence ----------------------------------------------
// Mid-edit form state survives a page refresh. Keyed by event id so
// editing two events in two tabs doesn't clobber each other; ``new``
// for the create form. Cleared on successful submit and on cancel.
const draftKey = computed(() => `event-form-draft:${props.eventId ?? "new"}`);

interface FormDraft {
  name: string;
  topic: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  eventDate: string | null;
  startTime: string | null;
  endTime: string | null;
  sources: string[];
  newSource: string;
  helpOptions: string[];
  newHelp: string;
  questionnaireEnabled: boolean;
  eventLocale: "nl" | "en";
}

function snapshot(): FormDraft {
  return {
    name: name.value,
    topic: topic.value,
    location: location.value,
    latitude: latitude.value,
    longitude: longitude.value,
    eventDate: eventDate.value?.toISOString() ?? null,
    startTime: startTime.value?.toISOString() ?? null,
    endTime: endTime.value?.toISOString() ?? null,
    sources: [...sources.value],
    newSource: newSource.value,
    helpOptions: [...helpOptions.value],
    newHelp: newHelp.value,
    questionnaireEnabled: questionnaireEnabled.value,
    eventLocale: eventLocale.value,
  };
}

function applyDraft(d: FormDraft) {
  name.value = d.name;
  topic.value = d.topic;
  location.value = d.location;
  latitude.value = d.latitude;
  longitude.value = d.longitude;
  eventDate.value = d.eventDate ? new Date(d.eventDate) : null;
  startTime.value = d.startTime ? new Date(d.startTime) : null;
  endTime.value = d.endTime ? new Date(d.endTime) : null;
  sources.value = [...d.sources];
  newSource.value = d.newSource;
  helpOptions.value = [...(d.helpOptions ?? [])];
  newHelp.value = d.newHelp ?? "";
  questionnaireEnabled.value = d.questionnaireEnabled;
  eventLocale.value = d.eventLocale ?? "nl";
}

function loadDraft(): FormDraft | null {
  try {
    const raw = localStorage.getItem(draftKey.value);
    return raw ? (JSON.parse(raw) as FormDraft) : null;
  } catch {
    return null;
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(draftKey.value);
  } catch {
    /* localStorage disabled — nothing to clean up */
  }
}

let _saveTimer: number | null = null;
watch(
  [name, topic, location, latitude, longitude, eventDate, startTime, endTime, sources, newSource, helpOptions, newHelp, questionnaireEnabled, eventLocale],
  () => {
    if (_saveTimer !== null) clearTimeout(_saveTimer);
    _saveTimer = window.setTimeout(() => {
      try {
        localStorage.setItem(draftKey.value, JSON.stringify(snapshot()));
      } catch {
        /* localStorage full or disabled — silently skip */
      }
    }, 200);
  },
  { deep: true },
);

function _timeAt(hours: number): Date {
  const d = new Date();
  d.setHours(hours, 0, 0, 0);
  return d;
}

function combine(date: Date, time: Date): Date {
  const d = new Date(date);
  d.setHours(time.getHours(), time.getMinutes(), 0, 0);
  return d;
}

function addSource() {
  const v = newSource.value.trim();
  if (!v || sources.value.includes(v)) return;
  sources.value.push(v);
  newSource.value = "";
}

function removeSource(i: number) {
  sources.value.splice(i, 1);
}

function addHelp() {
  const v = newHelp.value.trim();
  if (!v || helpOptions.value.includes(v)) return;
  helpOptions.value.push(v);
  newHelp.value = "";
}

function removeHelp(i: number) {
  helpOptions.value.splice(i, 1);
}

function cancel() {
  clearDraft();
  // Edit-mode bails back to the details view; create-mode bails to
  // the dashboard. Keeps the back-stack predictable instead of
  // relying on browser history.
  if (isEdit.value && props.eventId) {
    void router.push(`/events/${props.eventId}/details`);
  } else {
    void router.push("/dashboard");
  }
}

onMounted(async () => {
  // Always fetch chapters so ``chapterBias`` resolves the
  // organiser's home city for address suggestions.
  if (chapters.all.length === 0) await chapters.fetchAll();
  if (isEdit.value) {
    if (events.all.length === 0) await events.fetchAll();
    const existing = events.all.find((e) => e.id === props.eventId);
    if (!existing) {
      toasts.error(t("event.notFound"));
      return;
    }
    name.value = existing.name;
    topic.value = existing.topic ?? "";
    location.value = existing.location;
    latitude.value = existing.latitude;
    longitude.value = existing.longitude;
    const start = new Date(existing.starts_at);
    const end = new Date(existing.ends_at);
    eventDate.value = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    startTime.value = new Date(start);
    endTime.value = new Date(end);
    sources.value = [...existing.source_options];
    helpOptions.value = [...existing.help_options];
    questionnaireEnabled.value = existing.questionnaire_enabled;
    eventLocale.value = existing.locale;
  }
  // Restore mid-edit draft last so it overrides fetched values: the
  // user's most recent edits should win over the stored event.
  const draft = loadDraft();
  if (draft) applyDraft(draft);
});

async function submit() {
  const trimmedName = name.value.trim();
  const trimmedLocation = location.value.trim();
  if (!trimmedName) {
    toasts.warn(t("event.fillName"));
    return;
  }
  if (!trimmedLocation) {
    toasts.warn(t("event.fillLocation"));
    return;
  }
  if (!eventDate.value) {
    toasts.warn(t("event.fillDate"));
    return;
  }
  if (!startTime.value) {
    toasts.warn(t("event.fillStartTime"));
    return;
  }
  if (!endTime.value) {
    toasts.warn(t("event.fillEndTime"));
    return;
  }
  if (sources.value.length === 0) {
    toasts.warn(t("event.fillSources"));
    return;
  }
  const startsAt = combine(eventDate.value, startTime.value);
  const endsAt = combine(eventDate.value, endTime.value);
  if (endsAt <= startsAt) {
    toasts.warn(t("event.endAfterStart"));
    return;
  }
  submitting.value = true;
  try {
    const payload = {
      name: trimmedName,
      topic: topic.value.trim() || null,
      location: trimmedLocation,
      latitude: latitude.value,
      longitude: longitude.value,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      source_options: sources.value,
      help_options: helpOptions.value,
      questionnaire_enabled: questionnaireEnabled.value,
      locale: eventLocale.value,
    };
    const result =
      isEdit.value && props.eventId
        ? await events.update(props.eventId, payload)
        : await events.create(payload);
    clearDraft();
    void router.push(`/events/${result.id}/details`);
  } catch {
    // Validation feedback is handled up-front; everything else
    // collapses to a localised generic so users never see raw
    // Pydantic / FastAPI English.
    toasts.error(t("event.saveFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard tag="form" novalidate @submit.prevent="submit">
      <h1>{{ isEdit ? t("event.editTitle") : t("event.newTitle") }}</h1>

      <section class="form-section">
        <InputText v-model="name" :placeholder="t('event.name')" fluid />
        <InputText v-model="topic" :placeholder="t('event.topic')" fluid />
        <LocationPicker
          v-model="location"
          :latitude="latitude"
          :longitude="longitude"
          :bias-lat="chapterBias.lat"
          :bias-lon="chapterBias.lon"
          @update:coords="(c) => { latitude = c.latitude; longitude = c.longitude; }"
        />
        <DatePicker v-model="eventDate" date-format="dd-mm-yy" :placeholder="t('event.date')" fluid />
        <div class="time-row">
          <DatePicker
            v-model="startTime"
            time-only
            hour-format="24"
            :step-minute="15"
            :placeholder="t('event.startTime')"
            fluid
          />
          <DatePicker
            v-model="endTime"
            time-only
            hour-format="24"
            :step-minute="15"
            :placeholder="t('event.endTime')"
            fluid
          />
        </div>
      </section>

      <section class="form-section">
        <h2 class="section-heading">{{ t("event.sourcesHeading") }}</h2>
        <p class="muted section-explainer">{{ t("event.sourcesExplainer") }}</p>
        <EditableList
          :items="sources"
          :item-label="(s: string) => s"
          :item-key="(s: string) => s"
          @remove="(s: string) => removeSource(sources.indexOf(s))"
        >
          <template #add>
            <InputText
              v-model="newSource"
              :placeholder="t('event.newSource')"
              fluid
              @keydown.enter.prevent="addSource"
            />
            <Button
              icon="pi pi-plus"
              size="small"
              severity="secondary"
              :aria-label="t('event.newSource')"
              @click="addSource"
            />
          </template>
        </EditableList>
      </section>

      <section class="form-section">
        <h2 class="section-heading">{{ t("event.helpHeading") }}</h2>
        <p class="muted section-explainer">{{ t("event.helpExplainer") }}</p>
        <EditableList
          :items="helpOptions"
          :item-label="(s: string) => s"
          :item-key="(s: string) => s"
          @remove="(s: string) => removeHelp(helpOptions.indexOf(s))"
        >
          <template #add>
            <InputText
              v-model="newHelp"
              :placeholder="t('event.newHelp')"
              fluid
              @keydown.enter.prevent="addHelp"
            />
            <Button
              icon="pi pi-plus"
              size="small"
              severity="secondary"
              :aria-label="t('event.newHelp')"
              @click="addHelp"
            />
          </template>
        </EditableList>
      </section>

      <section class="form-section">
        <label class="toggle-row" for="questionnaireToggle">
          <ToggleSwitch v-model="questionnaireEnabled" inputId="questionnaireToggle" />
          <strong>{{ t("event.questionnaireToggle") }}</strong>
        </label>
        <p class="muted toggle-help">{{ t("event.questionnaireHelp") }}</p>
      </section>

      <section class="form-section">
        <h2 class="section-heading">{{ t("event.localeHeading") }}</h2>
        <p class="muted section-explainer">{{ t("event.localeExplainer") }}</p>
        <Select
          v-model="eventLocale"
          :options="[
            { value: 'nl', label: t('event.localeNl') },
            { value: 'en', label: t('event.localeEn') },
          ]"
          option-label="label"
          option-value="value"
          fluid
        />
      </section>

      <div class="form-footer">
        <Button
          :label="t('common.cancel')"
          severity="secondary"
          text
          type="button"
          @click="cancel"
        />
        <Button type="submit" :label="isEdit ? t('event.save') : t('event.create')" :loading="submitting" />
      </div>
    </AppCard>
  </div>
</template>

<style scoped>
/* Each labelled block (basics / sources / help / questionnaire /
 * locale) is a ``form-section``. Inside the section, fields stack
 * with the standard 0.75rem gap; between sections we open up
 * 2.5rem of breathing room so a glance can pick out the groups
 * without reading every line. */
.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.form-section + .form-section {
  margin-top: 2.5rem;
}
.time-row {
  display: flex;
  gap: 0.5rem;
}
.time-row > * {
  flex: 1;
}
.toggle-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  cursor: pointer;
}
.toggle-help {
  font-size: 0.8125rem;
}
.section-heading {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
}
/* Tight under the heading so heading + intro read as a single
 * unit, then the section's normal 0.75rem gap kicks in below. */
.section-explainer {
  margin: -0.25rem 0 0.25rem;
}
/* Same shape as AppDialog's footer — Cancel + primary action,
 * right-aligned, matched gap. The ``margin-top`` separates the
 * footer from the last section so Cancel / Submit don't feel
 * glued to the locale picker. */
.form-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.5rem;
}
</style>
