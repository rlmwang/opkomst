<script setup lang="ts">
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import Textarea from "primevue/textarea";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import FormPageShell from "@/components/FormPageShell.vue";
import ImageField from "@/components/ImageField.vue";
import { ApiError } from "@/api/client";
import { chapterList, useChapters } from "@/composables/useChapters";
import {
  type DatepollCreate,
  type DatepollUpdate,
  useCreateDatepoll,
  useDatepoll,
  useUpdateDatepoll,
} from "@/composables/useDatepolls";
import { useFormDraft } from "@/composables/useFormDraft";
import { localeTag } from "@/lib/format";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ datepollId?: string }>();

const { t, locale } = useI18n();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();
const chaptersQuery = useChapters();
const chapters = chapterList(chaptersQuery);
const auth = useAuthStore();
const createMutation = useCreateDatepoll();
const updateMutation = useUpdateDatepoll();

const isEdit = computed(() => Boolean(props.datepollId));

const chapterId = ref<string | null>(null);
const userChapterOptions = computed(() => {
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return chapters.value.filter((c) => memberIds.has(c.id));
});

// Drop a restored chapter the user can't actually assign — e.g. a
// localStorage draft saved before a DB reseed gave chapters new ids.
// Without this, submit would 403 on the chapter-membership check with
// a stale id the chapter <Select> can't even display.
watch(userChapterOptions, (opts) => {
  if (chapterId.value && opts.length && !opts.some((c) => c.id === chapterId.value)) {
    chapterId.value = opts.length === 1 ? opts[0].id : null;
  }
});

const name = ref("");
const description = ref("");
const imageUrl = ref<string | null>(null);
const imageArtistInstagram = ref("");
const imageField = ref<InstanceType<typeof ImageField> | null>(null);
const pollLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
// Candidate dates as ``Date`` objects (PrimeVue multiple-select).
const selectedDates = ref<Date[]>([]);
// Time-slots per day, keyed by ISO date. A day absent here (or with an
// empty list) is a whole-day candidate; otherwise each entry is one
// timed slot. ``newSlot[iso]`` holds the in-progress add-row inputs.
type TimeSlot = { start: string; end: string };
const slots = reactive<Record<string, TimeSlot[]>>({});
const newSlot = reactive<Record<string, TimeSlot>>({});
// Common time-slots applied to *every* selected day (a convenience for
// "same times each day"). They show on each day card and merge into the
// payload; a day's own ``slots[iso]`` are extras on top. ``newCommon``
// is the shared add-row buffer.
const commonSlots = ref<TimeSlot[]>([]);
const newCommon = reactive<TimeSlot>({ start: "", end: "" });
// Per-day exceptions: ``excluded[iso]`` lists the keys of common slots
// turned *off* for that one day (so "every day at 19:00 except the
// 14th" is one common slot + one exclusion).
const excluded = reactive<Record<string, string[]>>({});
const submitting = ref(false);

// --- Date <-> ISO helpers ------------------------------------------
// ``on_date`` is a whole calendar date; use local Y-M-D components so
// a date never shifts a day across the UTC boundary.
function toISODate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fromISODate(iso: string): Date {
  return new Date(`${iso}T00:00:00`);
}

const sortedISODates = computed(() =>
  [...selectedDates.value].map(toISODate).sort(),
);

function removeDate(iso: string): void {
  selectedDates.value = selectedDates.value.filter((d) => toISODate(d) !== iso);
  delete slots[iso];
  delete newSlot[iso];
  delete excluded[iso];
}

// Keep an add-row buffer for every selected day, and prune slot data
// for days that were deselected in the calendar.
watch(
  sortedISODates,
  (isos) => {
    const live = new Set(isos);
    for (const iso of isos) newSlot[iso] ??= { start: "", end: "" };
    for (const iso of Object.keys(slots)) if (!live.has(iso)) delete slots[iso];
    for (const iso of Object.keys(newSlot)) if (!live.has(iso)) delete newSlot[iso];
    for (const iso of Object.keys(excluded)) if (!live.has(iso)) delete excluded[iso];
  },
  { immediate: true },
);

// --- Time-slot editing ---------------------------------------------

/** Normalise a typed time to 24-hour ``HH:MM`` (no AM/PM, ever — the
 *  native time input can't be forced off the OS locale, so we own the
 *  field). Minutes default to ``00`` when omitted: ``19`` → ``19:00``,
 *  ``1930`` / ``19:30`` → ``19:30``, ``9`` → ``09:00``. Empty stays
 *  empty; out-of-range values clamp. */
function normalizeTime(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return "";
  const h = digits.length <= 2 ? digits : digits.slice(0, digits.length - 2);
  const m = digits.length <= 2 ? "0" : digits.slice(-2);
  const hh = Math.min(23, Math.max(0, parseInt(h, 10)));
  const mm = Math.min(59, Math.max(0, parseInt(m, 10)));
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** Time range as ``19:00–21:00`` for a slot pill. */
function slotLabel(s: TimeSlot): string {
  return `${s.start}–${s.end}`;
}

/** Validate + normalise an add-row draft into a slot, or null (with a
 *  toast) if it's incomplete/inverted/duplicate. ``existing`` is the
 *  list it's being added to, for the dup check. */
function buildSlot(draft: TimeSlot, existing: TimeSlot[]): TimeSlot | null {
  const start = normalizeTime(draft.start);
  const end = normalizeTime(draft.end);
  if (!start || !end) return null;
  if (end <= start) {
    toasts.warn(t("datepolls.edit.slotRangeInvalid"));
    return null;
  }
  if (existing.some((s) => s.start === start && s.end === end)) {
    toasts.warn(t("datepolls.edit.slotDuplicate"));
    return null;
  }
  return { start, end };
}

function addSlot(iso: string): void {
  const draft = newSlot[iso];
  if (!draft) return;
  // A day's own slots can't duplicate a common slot either.
  const slot = buildSlot(draft, [...commonSlots.value, ...(slots[iso] ?? [])]);
  if (!slot) return;
  const list = (slots[iso] ??= []);
  list.push(slot);
  list.sort((a, b) => a.start.localeCompare(b.start));
  newSlot[iso] = { start: "", end: "" };
}

function removeSlot(iso: string, index: number): void {
  slots[iso]?.splice(index, 1);
  if (slots[iso]?.length === 0) delete slots[iso];
}

function addCommonSlot(): void {
  const slot = buildSlot(newCommon, commonSlots.value);
  if (!slot) return;
  commonSlots.value = [...commonSlots.value, slot].sort((a, b) => a.start.localeCompare(b.start));
  newCommon.start = "";
  newCommon.end = "";
}

function slotKey(s: TimeSlot): string {
  return `${s.start}-${s.end}`;
}

/** Is a common slot active (not excluded) on this day? */
function isCommonOn(iso: string, s: TimeSlot): boolean {
  return !(excluded[iso] ?? []).includes(slotKey(s));
}

/** Toggle a common slot on/off for a single day. */
function toggleCommon(iso: string, s: TimeSlot): void {
  const key = slotKey(s);
  const list = (excluded[iso] ??= []);
  const i = list.indexOf(key);
  if (i >= 0) list.splice(i, 1);
  else list.push(key);
  if (list.length === 0) delete excluded[iso];
}

function removeCommonSlot(index: number): void {
  const removed = commonSlots.value[index];
  commonSlots.value = commonSlots.value.filter((_, i) => i !== index);
  if (!removed) return;
  // Drop now-orphaned exclusions for the removed slot.
  const key = slotKey(removed);
  for (const iso of Object.keys(excluded)) {
    excluded[iso] = excluded[iso].filter((k) => k !== key);
    if (excluded[iso].length === 0) delete excluded[iso];
  }
}

/** All slots that apply to a day: the common ones still active here,
 *  plus the day's own extras, in start order. Used for the payload. */
function effectiveSlots(iso: string): TimeSlot[] {
  const common = commonSlots.value.filter((s) => isCommonOn(iso, s));
  return [...common, ...(slots[iso] ?? [])].sort((a, b) => a.start.localeCompare(b.start));
}

// Compact chip label, e.g. "za 12 jul" — the long format is too wide
// for a pill.
function chipLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(localeTag(locale.value), {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

const existingQuery = computed(() => (props.datepollId ? props.datepollId : ""));
const pollQuery = isEdit.value ? useDatepoll(existingQuery) : null;

const notFound = computed(
  () =>
    isEdit.value &&
    pollQuery?.error.value instanceof ApiError &&
    pollQuery.error.value.status === 404,
);
const otherError = computed(
  () => isEdit.value && pollQuery?.error.value && !notFound.value,
);

watch(
  () => pollQuery?.data.value,
  (existing) => {
    if (!existing) return;
    name.value = existing.name;
    description.value = existing.description ?? "";
    imageUrl.value = existing.image_url ?? null;
    imageArtistInstagram.value = existing.image_artist_instagram ?? "";
    pollLocale.value = existing.locale;
    chapterId.value = existing.chapter_id;
    const existingSlots = existing.slots ?? [];
    selectedDates.value = [...new Set(existingSlots.map((s) => s.on_date))].map(fromISODate);
    for (const k of Object.keys(slots)) delete slots[k];
    for (const s of existingSlots) {
      if (s.start_time && s.end_time) {
        (slots[s.on_date] ??= []).push({ start: s.start_time.slice(0, 5), end: s.end_time.slice(0, 5) });
      }
    }
    restoreDraftOnce();
  },
  { immediate: true },
);

// --- Draft persistence ---------------------------------------------
const draftKey = computed(() => `datepoll-edit-draft:${props.datepollId ?? "new"}`);

interface DatepollDraft {
  name: string;
  description: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  pollLocale: "nl" | "en";
  dates: string[];
  slots: Record<string, TimeSlot[]>;
  commonSlots: TimeSlot[];
  excluded: Record<string, string[]>;
}

function snapshot(): DatepollDraft {
  return {
    name: name.value,
    description: description.value,
    imageArtistInstagram: imageArtistInstagram.value,
    chapterId: chapterId.value,
    pollLocale: pollLocale.value,
    dates: sortedISODates.value,
    slots: JSON.parse(JSON.stringify(slots)),
    commonSlots: commonSlots.value.map((s) => ({ ...s })),
    excluded: JSON.parse(JSON.stringify(excluded)),
  };
}

function applyDraft(d: DatepollDraft): void {
  name.value = d.name;
  description.value = d.description ?? "";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
  chapterId.value = d.chapterId ?? null;
  pollLocale.value = d.pollLocale ?? "nl";
  selectedDates.value = (d.dates ?? []).map(fromISODate);
  for (const k of Object.keys(slots)) delete slots[k];
  for (const [iso, list] of Object.entries(d.slots ?? {})) slots[iso] = list.map((s) => ({ ...s }));
  commonSlots.value = (d.commonSlots ?? []).map((s) => ({ ...s }));
  for (const k of Object.keys(excluded)) delete excluded[k];
  for (const [iso, keys] of Object.entries(d.excluded ?? {})) excluded[iso] = [...keys];
}

const { loadDraft, clearDraft } = useFormDraft<DatepollDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [
    name,
    description,
    imageArtistInstagram,
    chapterId,
    pollLocale,
    selectedDates,
    () => slots,
    commonSlots,
    () => excluded,
  ],
});

let draftRestored = false;
function restoreDraftOnce(): void {
  if (draftRestored) return;
  draftRestored = true;
  const draft = loadDraft();
  if (draft) applyDraft(draft);
}

onMounted(() => {
  if (isEdit.value) return;
  const queryChapter = (route.query.chapter as string | undefined) ?? null;
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (queryChapter && memberIds.has(queryChapter)) {
    chapterId.value = queryChapter;
  } else if (auth.user?.chapters?.length === 1) {
    chapterId.value = auth.user.chapters[0].id;
  }
  restoreDraftOnce();
});

// --- Cancel / submit -----------------------------------------------

function cancel(): void {
  clearDraft();
  if (isEdit.value && props.datepollId) {
    void router.push(`/datepolls/${props.datepollId}/details`);
  } else {
    void router.push("/datepolls");
  }
}

async function submit() {
  const trimmedName = name.value.trim();
  if (!trimmedName) {
    toasts.warn(t("datepolls.edit.fillName"));
    return;
  }
  if (!chapterId.value) {
    toasts.warn(t("datepolls.edit.fillChapter"));
    return;
  }
  submitting.value = true;
  try {
    // Each day with timed slots (common + its own) emits one slot per
    // range; a day with none emits a single whole-day slot (null times).
    const slotsPayload = sortedISODates.value.flatMap((iso) => {
      const timed = effectiveSlots(iso);
      return timed.length === 0
        ? [{ on_date: iso }]
        : timed.map((s) => ({ on_date: iso, start_time: s.start, end_time: s.end }));
    });
    const wirePayload: DatepollCreate | DatepollUpdate = {
      chapter_id: chapterId.value,
      name: trimmedName,
      description: description.value.trim() || null,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
      locale: pollLocale.value,
      slots: slotsPayload,
    };
    const result =
      isEdit.value && props.datepollId
        ? await updateMutation.mutateAsync({ datepollId: props.datepollId, payload: wirePayload })
        : await createMutation.mutateAsync(wirePayload);
    await imageField.value?.flushPendingUpload(result.id);
    clearDraft();
    void router.push(`/datepolls/${result.id}/details`);
  } catch {
    toasts.error(t("datepolls.edit.saveFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <template v-if="notFound">
    <AppHeader />
    <div class="container stack">
      <AppCard>
        <h2>{{ t("datepolls.edit.notFoundTitle") }}</h2>
        <p class="muted">{{ t("datepolls.edit.notFoundBody") }}</p>
        <router-link to="/datepolls" class="back-link">{{ t("datepolls.edit.backToList") }}</router-link>
      </AppCard>
    </div>
  </template>

  <template v-else-if="otherError">
    <AppHeader />
    <div class="container stack">
      <AppCard>
        <p>{{ t("datepolls.edit.loadFailed") }}</p>
      </AppCard>
    </div>
  </template>

  <FormPageShell
    v-else
    :title="isEdit ? t('datepolls.edit.editTitle') : t('datepolls.edit.newTitle')"
    :submit-label="isEdit ? t('datepolls.edit.save') : t('datepolls.edit.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
    <section class="form-section">
      <InputText v-model="name" :placeholder="t('datepolls.edit.namePlaceholder')" fluid />
      <Textarea
        v-model="description"
        :placeholder="t('datepolls.edit.descriptionPlaceholder')"
        rows="2"
        auto-resize
        fluid
      />
      <Select
        v-model="chapterId"
        :options="userChapterOptions"
        option-label="name"
        option-value="id"
        :placeholder="t('datepolls.edit.chapterPlaceholder')"
        :disabled="userChapterOptions.length === 1 && chapterId !== null"
        fluid
      />
    </section>

    <ImageField
      ref="imageField"
      resource="datepolls"
      :entity-id="props.datepollId ?? null"
      v-model:image-url="imageUrl"
      v-model:artist="imageArtistInstagram"
    />

    <section class="form-section">
      <h2 class="section-heading">{{ t("datepolls.edit.datesHeading") }}</h2>
      <p class="muted section-explainer">{{ t("datepolls.edit.datesExplainer") }}</p>

      <div class="dates-stack">
        <div class="picker-row">
          <DatePicker v-model="selectedDates" selection-mode="multiple" inline :manual-input="false" />

          <!-- Common time-slots: created once here, applied to every
               chosen day (shown on each day card below). -->
          <div class="common-panel">
            <p class="common-title">{{ t("datepolls.edit.commonSlotsTitle") }}</p>
            <p class="muted common-hint">{{ t("datepolls.edit.commonSlotsHint") }}</p>
            <div v-if="commonSlots.length" class="slot-pills">
              <button
                v-for="(s, idx) in commonSlots"
                :key="`${s.start}-${s.end}`"
                type="button"
                class="slot-pill"
                :aria-label="`${t('datepolls.edit.removeSlot')}: ${slotLabel(s)}`"
                @click="removeCommonSlot(idx)"
              >
                <span>{{ slotLabel(s) }}</span>
                <span class="x" aria-hidden="true">×</span>
              </button>
            </div>
            <div class="add-slot">
              <input
                v-model="newCommon.start"
                type="text"
                inputmode="numeric"
                placeholder="00:00"
                maxlength="5"
                class="time-input"
                :aria-label="t('datepolls.edit.slotStart')"
                @blur="newCommon.start = normalizeTime(newCommon.start)"
                @keyup.enter="newCommon.start = normalizeTime(newCommon.start)"
              />
              <span class="dash">–</span>
              <input
                v-model="newCommon.end"
                type="text"
                inputmode="numeric"
                placeholder="00:00"
                maxlength="5"
                class="time-input"
                :aria-label="t('datepolls.edit.slotEnd')"
                @blur="newCommon.end = normalizeTime(newCommon.end)"
                @keyup.enter="newCommon.end = normalizeTime(newCommon.end)"
              />
              <button type="button" class="add-slot-btn" @click="addCommonSlot">
                {{ t("datepolls.edit.addSlot") }}
              </button>
            </div>
          </div>
        </div>

        <p v-if="sortedISODates.length === 0" class="empty muted">
          {{ t("datepolls.edit.noDatesYet") }}
        </p>
        <!-- One card per chosen day: remove-day, its time-slot pills,
             and an add-row. A day with no time-slots stays whole-day
             (no label needed). -->
        <ul v-else class="day-cards">
          <li v-for="iso in sortedISODates" :key="iso" class="day-card">
            <div class="day-head">
              <span class="day-label">{{ chipLabel(iso) }}</span>
              <button
                type="button"
                class="remove-day"
                :aria-label="`${t('datepolls.edit.removeDate')}: ${chipLabel(iso)}`"
                @click="removeDate(iso)"
              >×</button>
            </div>

            <div v-if="commonSlots.length || slots[iso]?.length" class="slot-pills">
              <!-- Common slots apply to this day; tap to toggle one off
                   for this day only ("every day except this one"). -->
              <button
                v-for="s in commonSlots"
                :key="`c-${s.start}-${s.end}`"
                type="button"
                class="slot-pill common"
                :class="{ off: !isCommonOn(iso, s) }"
                :aria-pressed="isCommonOn(iso, s)"
                @click="toggleCommon(iso, s)"
              >
                {{ slotLabel(s) }}
              </button>
              <button
                v-for="(s, idx) in slots[iso]"
                :key="`${s.start}-${s.end}`"
                type="button"
                class="slot-pill"
                :aria-label="`${t('datepolls.edit.removeSlot')}: ${slotLabel(s)}`"
                @click="removeSlot(iso, idx)"
              >
                <span>{{ slotLabel(s) }}</span>
                <span class="x" aria-hidden="true">×</span>
              </button>
            </div>

            <div class="add-slot">
              <input
                v-model="newSlot[iso].start"
                type="text"
                inputmode="numeric"
                placeholder="00:00"
                maxlength="5"
                class="time-input"
                :aria-label="t('datepolls.edit.slotStart')"
                @blur="newSlot[iso].start = normalizeTime(newSlot[iso].start)"
                @keyup.enter="newSlot[iso].start = normalizeTime(newSlot[iso].start)"
              />
              <span class="dash">–</span>
              <input
                v-model="newSlot[iso].end"
                type="text"
                inputmode="numeric"
                placeholder="00:00"
                maxlength="5"
                class="time-input"
                :aria-label="t('datepolls.edit.slotEnd')"
                @blur="newSlot[iso].end = normalizeTime(newSlot[iso].end)"
                @keyup.enter="newSlot[iso].end = normalizeTime(newSlot[iso].end)"
              />
              <button type="button" class="add-slot-btn" @click="addSlot(iso)">
                {{ t("datepolls.edit.addSlot") }}
              </button>
            </div>
          </li>
        </ul>
      </div>
    </section>

    <section class="form-section">
      <h2 class="section-heading">{{ t("datepolls.edit.localeHeading") }}</h2>
      <p class="muted section-explainer">{{ t("datepolls.edit.localeExplainer") }}</p>
      <Select
        v-model="pollLocale"
        :options="[
          { value: 'nl', label: t('datepolls.edit.localeNl') },
          { value: 'en', label: t('datepolls.edit.localeEn') },
        ]"
        option-label="label"
        option-value="value"
        fluid
      />
    </section>
  </FormPageShell>
</template>

<style scoped>
/* Pin the inline date picker to a constant 6-week height (weekday
 * header + 6 rows) so navigating between 5- and 6-row months doesn't
 * shift the page. The day-view table sits at the top of the
 * container; a shorter month leaves the 6th-row slot empty rather
 * than collapsing. Row height = the theme's date-cell height + its
 * vertical padding (falls back to Aura's values). */
:deep(.p-datepicker-calendar-container) {
  min-height: calc((var(--p-datepicker-date-height, 2.5rem) + var(--p-datepicker-date-padding, 0.25rem) * 2) * 7);
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.form-section + .form-section {
  margin-top: 2.5rem;
}
.section-heading {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
}
.section-explainer {
  margin: -0.25rem 0 0.25rem;
}
/* Calendar on top, the chosen-days list below — one card per day,
 * each holding its time-slots inline (a day with none stays whole-day,
 * no label). */
.dates-stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: flex-start;
}
/* Calendar + the "times for all days" panel side by side; stack on
 * narrow screens. */
.picker-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem 1.5rem;
  align-items: flex-start;
  width: 100%;
}
.common-panel {
  flex: 1 1 14rem;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.common-title { margin: 0; font-weight: 600; font-size: 0.9375rem; }
.common-hint { margin: 0; font-size: 0.8125rem; }
/* A common slot on a day card — togglable: ON applies to this day,
 * OFF (struck through) excludes it from this day only. */
.slot-pill.common.off {
  text-decoration: line-through;
  opacity: 0.55;
  border-style: dashed;
  color: var(--brand-text-muted);
}
.day-cards {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.day-card {
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  padding: 0.625rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.day-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.day-label { font-weight: 600; font-size: 0.9375rem; text-transform: capitalize; }
.remove-day {
  border: none;
  background: none;
  color: var(--brand-text-muted);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 0.25rem;
}
.remove-day:hover { color: var(--brand-red); }
.slot-pills { display: flex; flex-wrap: wrap; gap: 0.375rem; }
.slot-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem 0.25rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  white-space: nowrap;
}
.slot-pill:hover { border-color: var(--brand-red); }
.slot-pill .x { color: var(--brand-text-muted); font-size: 1rem; line-height: 1; }
.slot-pill:hover .x { color: var(--brand-red); }
.add-slot { display: flex; align-items: center; gap: 0.375rem; flex-wrap: wrap; }
.time-input {
  font: inherit;
  font-size: 0.875rem;
  width: 4rem;
  text-align: center;
  padding: 0.25rem 0.375rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-bg);
  color: var(--brand-text);
}
.dash { color: var(--brand-text-muted); }
.add-slot-btn {
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
  border-radius: 6px;
  padding: 0.25rem 0.625rem;
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}
.add-slot-btn:hover { border-color: var(--brand-red); color: var(--brand-red); }
.empty {
  padding: 0.875rem 1rem;
  border: 1px dashed var(--brand-border);
  border-radius: 8px;
  font-style: italic;
}
.back-link {
  display: inline-block;
  margin-top: 0.5rem;
  color: var(--brand-red);
}
</style>
