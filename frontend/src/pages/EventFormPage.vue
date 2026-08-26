<script setup lang="ts">
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import CycleGridPicker from "@/components/CycleGridPicker.vue";
import EditableList from "@/components/EditableList.vue";
import FormPageShell from "@/components/FormPageShell.vue";
import ImageField from "@/components/ImageField.vue";
import LocationPicker from "@/components/LocationPicker.vue";
import NumberStepper from "@/components/NumberStepper.vue";
import RichTextField from "@/components/RichTextField.vue";
import StartAccountField from "@/components/StartAccountField.vue";
import StartedPanel from "@/components/StartedPanel.vue";
import { chapterList, useChapters } from "@/composables/useChapters";
import { useStartMode } from "@/composables/useStartMode";
import { useBilingualField } from "@/composables/useBilingualField";
import { useLocationField } from "@/composables/useLocationField";
import {
  eventList,
  useCreateEvent,
  useEventList,
  useUpdateEvent,
} from "@/composables/useEvents";
import { firstFieldError } from "@/api/client";
import { useFormDraft } from "@/composables/useFormDraft";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ eventId?: string }>();

const { t, te, locale } = useI18n();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();
// Opened from the root's landing tiles by somebody with no account:
// an address field on top, no chapter picker, and the start endpoint
// as the target. ``hasChapters`` is false for a personal account too,
// signed in or not — it has none to pick from.
const {
  active: startActive,
  hasChapters,
  email: startEmail,
  started,
  validate: validateStartEmail,
  submit: submitStart,
  chapterFor,
  cancel: cancelStart,
} = useStartMode("event");
const chaptersQuery = useChapters({ enabled: hasChapters });
const chapters = chapterList(chaptersQuery);
const isEdit = computed(() => Boolean(props.eventId));
// The list is read for one thing only: pulling the row being edited
// out of the cache. Create mode never needs it, and at the root there
// is no session to read it with.
const eventsQuery = useEventList({ enabled: isEdit });
const events = eventList(eventsQuery);
const createMutation = useCreateEvent();
const updateMutation = useUpdateEvent();
const auth = useAuthStore();

// Live ``image_url`` for the event being edited; ``null`` in create
// mode. Bound to the shared ImageField, which owns the upload/remove
// flow and writes back here so the preview updates instantly.
const imageUrl = ref<string | null>(null);
const imageField = ref<InstanceType<typeof ImageField> | null>(null);

// Chapter the event is being assigned to. The dropdown options
// are scoped to ``auth.user.chapters`` — admins are not exempt;
// they pick from their own membership for their own events
// (the rule deliberately constrains everyone, to reduce
// cognitive load + misclicks). Pre-fill on create from the
// ``?chapter=`` query param so opening "New event" while
// filtered to chapter X lands on X.
const chapterId = ref<string | null>(null);

const userChapterOptions = computed(() => {
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return chapters.value.filter((c) => memberIds.has(c.id));
});

// Location + coords + chapter-city geocoder bias — shared with the
// datepoll editor via ``useLocationField``. Bias resolves from the
// chapters store rather than the cached auth.user copy so a chapter
// that gets a city assigned mid-session flows through without a
// re-login.
const { location, latitude, longitude, chapterBias, setCoords } = useLocationField(
  () => chapterId.value,
  () => chapters.value,
);

const nameNl = ref("");
const nameEn = ref("");
const topicNl = ref("");
const topicEn = ref("");
const { active: title, fallback: titleFallback } = useBilingualField(nameNl, nameEn);
const { active: body, fallback: bodyFallback } = useBilingualField(topicNl, topicEn);
const eventDate = ref<Date | null>(null);
// Most events run in the evening — pre-fill 20:00 / 22:00 so the
// organiser only has to pick the date and tweak if needed. The date
// portion is irrelevant (``combine()`` merges the picked date with
// these times before save). Edit-mode and the draft restore both
// overwrite these defaults below.
const startTime = ref<Date | null>(_timeAt(20));
const endTime = ref<Date | null>(_timeAt(22));

// --- Recurrence rule (the roster's k-week cycle) ---------------------
// The date + time pickers above fix the anchor (start date) and the
// shared time of day. ``repeats`` reveals the recurrence controls: a
// ``periodWeeks`` cycle length (the CycleGridPicker's week-rows), the
// ``cycleSlots`` weekday grid, and a span — ``spanWeeks`` weeks unless
// ``openEnded`` (doorlopend). A one-off is ``repeats === false`` (empty
// ``cycle_slots``). ``horizon_days`` is a fixed 90-day materialisation
// window — no UI control (see submit()).
const repeats = ref(false);
const periodWeeks = ref(1);
const cycleSlots = ref<number[]>([]);
const spanWeeks = ref(6);
const openEnded = ref(false);

// Lowering the cycle length drops now-out-of-range weekday offsets, so
// the payload never carries a slot the shorter cycle can't hold (mirrors
// ChoresEditPage).
watch(periodWeeks, (next, prev) => {
  if (next >= prev) return;
  const hi = 7 * next;
  cycleSlots.value = cycleSlots.value.filter((s) => s < hi);
});

// Map the controls onto the wire fields.
const wirePeriodWeeks = computed(() => (repeats.value ? Math.max(1, Math.floor(periodWeeks.value || 1)) : 1));
const wireCycleSlots = computed(() => (repeats.value ? cycleSlots.value : []));
const wireSpanWeeks = computed<number | null>(() => {
  if (!repeats.value || openEnded.value) return null;
  return Math.max(1, Math.floor(spanWeeks.value || 1));
});
// Default ``How did you find us?`` options, ordered by typical
// frequency for grassroots events (word of mouth dominates, posters
// are the long tail) and seeded in the organiser's current locale.
// Stored as plain strings on the event — once saved they don't
// auto-translate, but the organiser can rename or remove any of them
// before saving.
// Default option sets for both editable lists are derived from the
// *event* locale (not the UI locale). The public form is rendered in
// the event's language, so the seeded options should match — picking
// English in the UI shouldn't lock the form to English options when
// the organiser is creating a Dutch-language event.
function defaultSources(loc: "nl" | "en"): string[] {
  return [
    t("event.sourceDefaults.wordOfMouth", 1, { locale: loc }),
    t("event.sourceDefaults.socialMedia", 1, { locale: loc }),
    t("event.sourceDefaults.flyer", 1, { locale: loc }),
    t("event.sourceDefaults.poster", 1, { locale: loc }),
  ];
}
function defaultHelp(loc: "nl" | "en"): string[] {
  return [
    t("event.helpDefaults.setup", 1, { locale: loc }),
    t("event.helpDefaults.teardown", 1, { locale: loc }),
  ];
}
function arraysEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}
// The two optional questions on the public sign-up form, each with its
// own switch. Off means the question isn't asked at all; the options
// stay where they are, so switching one back on brings the organiser's
// own list back rather than an empty one.
const sources = ref<string[]>(defaultSources(((locale.value as "nl" | "en") ?? "nl")));
const newSource = ref("");
const sourceEnabled = ref(false);
const helpOptions = ref<string[]>(defaultHelp(((locale.value as "nl" | "en") ?? "nl")));
const newHelp = ref("");
const helpEnabled = ref(false);
// Instagram handle of the artist credited on the hero image.
// Stored without ``@``; the backend's schema validator strips
// one if present, so paste-friendliness on the form side is
// fine.
const imageArtistInstagram = ref("");
const feedbackEnabled = ref(false);
const reminderEnabled = ref(false);
const listed = ref(false);
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
  nameNl: string;
  nameEn: string;
  chapterId: string | null;
  topicNl: string;
  topicEn: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  eventDate: string | null;
  startTime: string | null;
  endTime: string | null;
  repeats: boolean;
  periodWeeks: number;
  cycleSlots: number[];
  spanWeeks: number;
  openEnded: boolean;
  sources: string[];
  newSource: string;
  sourceEnabled: boolean;
  helpOptions: string[];
  newHelp: string;
  helpEnabled: boolean;
  feedbackEnabled: boolean;
  reminderEnabled: boolean;
  listed: boolean;
  eventLocale: "nl" | "en";
  imageArtistInstagram: string;
}

function snapshot(): FormDraft {
  return {
    nameNl: nameNl.value,
    nameEn: nameEn.value,
    chapterId: chapterId.value,
    topicNl: topicNl.value,
    topicEn: topicEn.value,
    location: location.value,
    latitude: latitude.value,
    longitude: longitude.value,
    eventDate: eventDate.value?.toISOString() ?? null,
    startTime: startTime.value?.toISOString() ?? null,
    endTime: endTime.value?.toISOString() ?? null,
    repeats: repeats.value,
    periodWeeks: periodWeeks.value,
    cycleSlots: [...cycleSlots.value],
    spanWeeks: spanWeeks.value,
    openEnded: openEnded.value,
    sources: [...sources.value],
    newSource: newSource.value,
    sourceEnabled: sourceEnabled.value,
    helpOptions: [...helpOptions.value],
    newHelp: newHelp.value,
    helpEnabled: helpEnabled.value,
    feedbackEnabled: feedbackEnabled.value,
    reminderEnabled: reminderEnabled.value,
    listed: listed.value,
    eventLocale: eventLocale.value,
    imageArtistInstagram: imageArtistInstagram.value,
  };
}

function applyDraft(d: FormDraft) {
  nameNl.value = d.nameNl ?? "";
  nameEn.value = d.nameEn ?? "";
  chapterId.value = d.chapterId ?? null;
  topicNl.value = d.topicNl ?? "";
  topicEn.value = d.topicEn ?? "";
  location.value = d.location;
  latitude.value = d.latitude;
  longitude.value = d.longitude;
  eventDate.value = d.eventDate ? new Date(d.eventDate) : null;
  startTime.value = d.startTime ? new Date(d.startTime) : null;
  endTime.value = d.endTime ? new Date(d.endTime) : null;
  repeats.value = d.repeats ?? false;
  periodWeeks.value = d.periodWeeks ?? 1;
  cycleSlots.value = [...(d.cycleSlots ?? [])];
  spanWeeks.value = d.spanWeeks ?? 6;
  openEnded.value = d.openEnded ?? false;
  sources.value = [...d.sources];
  newSource.value = d.newSource;
  sourceEnabled.value = d.sourceEnabled ?? false;
  helpOptions.value = [...(d.helpOptions ?? [])];
  newHelp.value = d.newHelp ?? "";
  helpEnabled.value = d.helpEnabled ?? false;
  feedbackEnabled.value = d.feedbackEnabled;
  reminderEnabled.value = d.reminderEnabled ?? false;
  listed.value = d.listed ?? false;
  eventLocale.value = d.eventLocale ?? "nl";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
}

const { loadDraft, clearDraft } = useFormDraft<FormDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [
    nameNl, nameEn, chapterId, topicNl, topicEn, location, latitude, longitude, eventDate, startTime, endTime,
    repeats, periodWeeks, cycleSlots, spanWeeks, openEnded,
    sources, newSource, sourceEnabled, helpOptions, newHelp, helpEnabled,
    feedbackEnabled, reminderEnabled, listed, eventLocale, imageArtistInstagram,
  ],
});

function _timeAt(hours: number): Date {
  const d = new Date();
  d.setHours(hours, 0, 0, 0);
  return d;
}

// Parse a naive ``HH:MM:SS`` time into a Date (date portion irrelevant —
// only the DatePicker's time part is read back out).
function _timeFromString(hms: string): Date {
  const [h, m] = hms.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d;
}

function combine(date: Date, time: Date): Date {
  const d = new Date(date);
  d.setHours(time.getHours(), time.getMinutes(), 0, 0);
  return d;
}

// Backend stores event date + times as naive wall-clock (the user types
// 18:00, we send 18:00, the email later shows 18:00) — no zone suffix.
// ``sv-SE`` locale gives ``YYYY-MM-DD`` / ``HH:MM:SS`` from local time.
function naiveDate(d: Date): string {
  return d.toLocaleDateString("sv-SE");
}
function naiveTime(d: Date): string {
  return d.toLocaleTimeString("sv-SE");
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

// When the organiser flips the event language, swap the default
// option sets too — but only if the lists haven't been customised
// yet. An organiser who has added or removed options has clearly
// thought about the wording and we shouldn't clobber that.
watch(eventLocale, (next, prev) => {
  if (next === prev) return;
  if (arraysEqual(sources.value, defaultSources(prev))) {
    sources.value = defaultSources(next);
  }
  if (arraysEqual(helpOptions.value, defaultHelp(prev))) {
    helpOptions.value = defaultHelp(next);
  }
});

function cancel() {
  clearDraft();
  if (cancelStart()) return;
  // Edit-mode bails back to the details view; create-mode bails to
  // the dashboard. Keeps the back-stack predictable instead of
  // relying on browser history.
  if (isEdit.value && props.eventId) {
    void router.push(`/events/${props.eventId}/details`);
  } else {
    void router.push("/events");
  }
}

onMounted(async () => {
  // Always fetch chapters so ``chapterBias`` resolves the
  // organiser's home city for address suggestions.
  // chaptersQuery auto-fetches on first use; nothing to do here.
  if (isEdit.value) {
    // Wait for the events list to settle so we can pull the existing
    // row out of the cache. ``isPending`` is true on first fetch and
    // false once the query has resolved (success or failure).
    await new Promise<void>((resolve) => {
      if (!eventsQuery.isPending.value) {
        resolve();
        return;
      }
      const stop = watch(eventsQuery.isPending, (pending) => {
        if (!pending) {
          stop();
          resolve();
        }
      });
    });
    const existing = events.value.find((e) => e.id === props.eventId);
    if (!existing) {
      toasts.error(t("event.notFound"));
      return;
    }
    nameNl.value = existing.name_nl ?? "";
    nameEn.value = existing.name_en ?? "";
    chapterId.value = existing.chapter_id ?? null;
    topicNl.value = existing.topic_nl ?? "";
    topicEn.value = existing.topic_en ?? "";
    location.value = existing.location ?? "";
    latitude.value = existing.latitude;
    longitude.value = existing.longitude;
    // ``starts_on`` is a date, ``start_time`` / ``end_time`` are times.
    const [sy, sm, sd] = existing.starts_on.split("-").map(Number);
    eventDate.value = new Date(sy, sm - 1, sd);
    startTime.value = _timeFromString(existing.start_time);
    endTime.value = _timeFromString(existing.end_time);
    // Reverse-map the recurrence rule onto the controls.
    repeats.value = existing.cycle_slots.length > 0;
    periodWeeks.value = existing.period_weeks;
    cycleSlots.value = [...existing.cycle_slots];
    openEnded.value = existing.span_weeks === null;
    spanWeeks.value = existing.span_weeks ?? 6;
    sources.value = [...existing.source_options];
    sourceEnabled.value = existing.source_enabled;
    helpOptions.value = [...existing.help_options];
    helpEnabled.value = existing.help_enabled;
    feedbackEnabled.value = existing.feedback_enabled;
    reminderEnabled.value = existing.reminder_enabled;
    listed.value = existing.listed;
    eventLocale.value = existing.locale;
    imageUrl.value = existing.image_url;
    imageArtistInstagram.value = existing.image_artist_instagram ?? "";
  } else {
    // Create mode — prefill the chapter dropdown.
    //   1. ``?chapter=…`` from the dashboard's filter ("New event"
    //      opened while filtered to chapter X lands on X).
    //   2. If the user belongs to exactly one chapter, lock to it.
    //   3. Otherwise leave null and force an explicit pick.
    const queryChapter = (route.query.chapter as string | undefined) ?? null;
    const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
    if (queryChapter && memberIds.has(queryChapter)) {
      chapterId.value = queryChapter;
    } else if (auth.user?.chapters?.length === 1) {
      chapterId.value = auth.user.chapters[0].id;
    }
  }
  // Restore mid-edit draft last so it overrides fetched values: the
  // user's most recent edits should win over the stored event.
  const draft = loadDraft();
  if (draft) applyDraft(draft);
});

async function submit() {
  // Backend requires the title in the primary language (``eventLocale``).
  const primaryName = (eventLocale.value === "en" ? nameEn.value : nameNl.value).trim();
  const trimmedLocation = location.value.trim();
  if (!primaryName) {
    toasts.warn(t("event.fillName"));
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
  // A question that is being asked needs something to pick; one that
  // is switched off needs nothing.
  if (sourceEnabled.value && sources.value.length === 0) {
    toasts.warn(t("event.fillSources"));
    return;
  }
  if (helpEnabled.value && helpOptions.value.length === 0) {
    toasts.warn(t("event.fillHelp"));
    return;
  }
  if (hasChapters.value && !chapterId.value) {
    toasts.warn(t("event.fillChapter"));
    return;
  }
  if (startActive.value && !validateStartEmail()) return;
  const startsAt = combine(eventDate.value, startTime.value);
  const endsAt = combine(eventDate.value, endTime.value);
  if (endsAt <= startsAt) {
    toasts.warn(t("event.endAfterStart"));
    return;
  }
  if (repeats.value && wireCycleSlots.value.length === 0) {
    toasts.warn(t("event.fillCycleSlots"));
    return;
  }
  submitting.value = true;
  try {
    const payload = {
      name_nl: nameNl.value.trim() || null,
      name_en: nameEn.value.trim() || null,
      chapter_id: chapterFor(chapterId.value),
      topic_nl: topicNl.value.trim() || null,
      topic_en: topicEn.value.trim() || null,
      location: trimmedLocation || null,
      latitude: latitude.value,
      longitude: longitude.value,
      starts_on: naiveDate(eventDate.value),
      start_time: naiveTime(startTime.value),
      end_time: naiveTime(endTime.value),
      period_weeks: wirePeriodWeeks.value,
      cycle_slots: wireCycleSlots.value,
      span_weeks: wireSpanWeeks.value,
      horizon_days: 90,
      source_options: sources.value,
      source_enabled: sourceEnabled.value,
      help_options: helpOptions.value,
      help_enabled: helpEnabled.value,
      feedback_enabled: feedbackEnabled.value,
      reminder_enabled: reminderEnabled.value,
      listed: listed.value,
      locale: eventLocale.value,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
    };
    if (startActive.value) {
      // No session, so no details page to land on and no image to
      // flush onto the new row: the public link the response carries
      // is the whole result, and ``StartedPanel`` shows it. A refusal
      // has already been explained by ``submitStart``, and the draft
      // stays so the visitor can act on it and try again.
      if (await submitStart(payload)) clearDraft();
      return;
    }
    const result =
      isEdit.value && props.eventId
        ? await updateMutation.mutateAsync({ eventId: props.eventId, payload })
        : await createMutation.mutateAsync(payload);
    // Upload a create-mode held image to the freshly-created row
    // (no-op in edit mode / when nothing was picked).
    await imageField.value?.flushPendingUpload(result.id);
    clearDraft();
    void router.push(`/events/${result.id}/details`);
  } catch (err) {
    // Most validation is caught up-front; a field-level 422 that slips
    // through (e.g. a paste over the length cap) is surfaced with the
    // offending field named in the user's language, never raw Pydantic
    // English. Anything else collapses to the generic.
    const fe = firstFieldError(err);
    const label = fe && te(`event.fields.${fe.field}`) ? t(`event.fields.${fe.field}`) : null;
    if (fe && label && fe.type === "string_too_long" && fe.limit != null) {
      toasts.error(t("event.tooLong", { field: label, max: fe.limit }));
    } else if (fe && label) {
      toasts.error(t("event.invalidField", { field: label }));
    } else {
      toasts.error(t("event.saveFailed"));
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <StartedPanel v-if="started" :started="started" :email="startEmail" />
  <FormPageShell
    v-else
    :title="isEdit ? t('event.editTitle') : t('event.newTitle')"
    :submit-label="isEdit ? t('event.save') : t('event.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
      <section class="form-section">
        <StartAccountField v-if="startActive" v-model="startEmail" />
        <InputText
          v-model="title"
          :placeholder="titleFallback || t('event.name')"
          fluid
        />
        <RichTextField
          v-model="body"
          :placeholder="t('event.topic')"
          :fallback-html="bodyFallback || null"
        />
        <Select
          v-if="hasChapters"
          v-model="chapterId"
          :options="userChapterOptions"
          option-label="name"
          option-value="id"
          :placeholder="t('event.chapter')"
          :disabled="userChapterOptions.length === 1 && chapterId !== null"
          fluid
        />
        <LocationPicker
          v-model="location"
          :latitude="latitude"
          :longitude="longitude"
          :bias-lat="chapterBias.lat"
          :bias-lon="chapterBias.lon"
          @update:coords="setCoords"
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

      <!-- Uploading a picture writes to the row it belongs to, which
           takes a session; a visitor starting from the root doesn't
           have one yet. They add it after signing in through the link
           they were mailed. -->
      <ImageField
        v-if="!startActive"
        ref="imageField"
        resource="events"
        :entity-id="props.eventId ?? null"
        v-model:image-url="imageUrl"
        v-model:artist="imageArtistInstagram"
      />

      <section class="form-section">
        <!-- The switch turns the whole block on, so it sits in front of
             the heading rather than on a line of its own under it. -->
        <label class="toggle-row section-toggle" for="repeatToggle">
          <ToggleSwitch v-model="repeats" inputId="repeatToggle" />
          <h2 class="section-heading">{{ t("event.repeatHeading") }}</h2>
        </label>
        <p class="muted section-explainer">{{ t("event.repeatExplainer") }}</p>

        <template v-if="repeats">
          <div class="repeat-row">
            <span class="repeat-label">{{ t("event.repeat.everyLead") }}</span>
            <NumberStepper v-model="periodWeeks" :min="1" :max="8" :aria-label="t('event.repeat.everyWeeks')" />
            <span class="repeat-label">{{ t("event.repeat.everyTrail") }}</span>
          </div>

          <p class="muted section-explainer">{{ t("event.repeat.gridExplainer") }}</p>
          <CycleGridPicker v-model="cycleSlots" :period-weeks="periodWeeks" />

          <label class="toggle-row">
            <ToggleSwitch v-model="openEnded" />
            <span>{{ t("event.span.openEnded") }}</span>
          </label>
          <div v-if="!openEnded" class="repeat-row">
            <span class="repeat-label">{{ t("event.span.forLead") }}</span>
            <NumberStepper v-model="spanWeeks" :min="1" :max="104" :aria-label="t('event.span.weeks')" />
            <span class="repeat-label">{{ t("event.span.weeksTrail") }}</span>
          </div>
          <p v-else class="muted section-explainer">{{ t("event.span.openEndedHelp") }}</p>
        </template>
      </section>

      <!-- What people can offer comes before where they heard about it:
           one is about the event itself, the other is about us. -->
      <section class="form-section">
        <label class="toggle-row section-toggle" for="helpToggle">
          <ToggleSwitch v-model="helpEnabled" inputId="helpToggle" />
          <h2 class="section-heading">{{ t("event.helpHeading") }}</h2>
        </label>
        <p class="muted section-explainer">{{ t("event.helpExplainer") }}</p>
        <EditableList
          v-if="helpEnabled"
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
              type="button"
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
        <label class="toggle-row section-toggle" for="sourcesToggle">
          <ToggleSwitch v-model="sourceEnabled" inputId="sourcesToggle" />
          <h2 class="section-heading">{{ t("event.sourcesHeading") }}</h2>
        </label>
        <p class="muted section-explainer">{{ t("event.sourcesExplainer") }}</p>
        <EditableList
          v-if="sourceEnabled"
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
              type="button"
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
        <label class="toggle-row" for="reminderToggle">
          <ToggleSwitch v-model="reminderEnabled" inputId="reminderToggle" />
          <strong>{{ t("event.reminderToggle") }}</strong>
        </label>
        <p class="muted toggle-help">{{ t("event.reminderHelp") }}</p>

        <label class="toggle-row" for="questionnaireToggle">
          <ToggleSwitch v-model="feedbackEnabled" inputId="questionnaireToggle" />
          <strong>{{ t("event.questionnaireToggle") }}</strong>
        </label>
        <p class="muted toggle-help">{{ t("event.questionnaireHelp") }}</p>

        <!-- The agenda this lists on is a chapter's. An account with no
             chapters has no agenda to be on, so there is no choice to
             offer. -->
        <template v-if="hasChapters">
          <label class="toggle-row" for="listedToggle">
            <ToggleSwitch v-model="listed" inputId="listedToggle" />
            <strong>{{ t("event.listedToggle") }}</strong>
          </label>
          <p class="muted toggle-help">{{ t("event.listedHelp") }}</p>
        </template>
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

  </FormPageShell>
</template>

<style scoped>
/* Shared form chrome (.form-section, .section-heading,
 * .section-explainer, .toggle-row, .toggle-help) lives in
 * ``src/assets/forms.css``. Only event-specific rules stay here. */
.time-row {
  display: flex;
  gap: 0.5rem;
}
.time-row > * {
  flex: 1;
}
/* Recurrence rows: a stepper flanked by inline labels ("elke … weken",
 * "… sessies"). */
.repeat-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.repeat-label {
  color: var(--brand-text-muted);
}
/* Footer (Cancel + Save buttons) is owned by FormPageShell —
 * see ``FormPageShell.vue::.form-footer``. */
</style>
