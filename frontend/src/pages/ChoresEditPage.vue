<script setup lang="ts">
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import ChoreEditor, { type ChoreDraft } from "@/components/ChoreEditor.vue";
import { DEFAULT_CHORE_EMOJI, firstUnusedEmoji } from "@/components/EmojiPicker.vue";
import FormPageShell from "@/components/FormPageShell.vue";
import ImageField from "@/components/ImageField.vue";
import NumberStepper from "@/components/NumberStepper.vue";
import RichTextField from "@/components/RichTextField.vue";
import { ApiError } from "@/api/client";
import type { ChoreIn, RosterCreate, RosterUpdate } from "@/api/types";
import StartAccountField from "@/components/StartAccountField.vue";
import StartedPanel from "@/components/StartedPanel.vue";
import { chapterList, useChapters } from "@/composables/useChapters";
import { useStartMode } from "@/composables/useStartMode";
import { useBilingualField } from "@/composables/useBilingualField";
import { useCreateRoster, useRoster, useUpdateRoster } from "@/composables/useChores";
import { useFormDraft } from "@/composables/useFormDraft";
import { useOrderedList } from "@/composables/useOrderedList";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ rosterId?: string }>();

const { t, locale } = useI18n();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();
// The root's front door: see ``useStartMode``.
const {
  active: startActive,
  hasChapters,
  email: startEmail,
  started,
  validate: validateStartEmail,
  submit: submitStart,
  chapterFor,
  cancel: cancelStart,
} = useStartMode("roster");
const chaptersQuery = useChapters({ enabled: hasChapters });
const chapters = chapterList(chaptersQuery);
const auth = useAuthStore();
const createMutation = useCreateRoster();
const updateMutation = useUpdateRoster();

const isEdit = computed(() => Boolean(props.rosterId));

const chapterId = ref<string | null>(null);
const userChapterOptions = computed(() => {
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return chapters.value.filter((c) => memberIds.has(c.id));
});

const nameNl = ref("");
const nameEn = ref("");
const descNl = ref("");
const descEn = ref("");
const { active: title, fallback: titleFallback } = useBilingualField(nameNl, nameEn);
const { active: body, fallback: bodyFallback } = useBilingualField(descNl, descEn);
const imageUrl = ref<string | null>(null);
const imageArtistInstagram = ref("");
const imageField = ref<InstanceType<typeof ImageField> | null>(null);
const rosterLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
const periodWeeks = ref(1);
const startsOn = ref<Date | null>(null);
const endsOn = ref<Date | null>(null);
const reminderEnabled = ref(true);
const reminderDaysBefore = ref(1);
const commitHorizonDays = ref(21);
const choreListState = useOrderedList<ChoreDraft>();
const chores = choreListState.items;
const submitting = ref(false);

const localeOptions = computed(() => [
  { value: "nl", label: t("chores.edit.localeNl") },
  { value: "en", label: t("chores.edit.localeEn") },
]);

// --- Date <-> "YYYY-MM-DD" (local, no UTC shift) --------------------
function isoDate(d: Date | null): string | null {
  if (!d) return null;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

const existingQuery = computed(() => (props.rosterId ? props.rosterId : ""));
const rosterQuery = isEdit.value ? useRoster(existingQuery) : null;

const notFound = computed(
  () =>
    isEdit.value &&
    rosterQuery?.error.value instanceof ApiError &&
    rosterQuery.error.value.status === 404,
);
const otherError = computed(() => isEdit.value && rosterQuery?.error.value && !notFound.value);

// The concrete date cycle week 0 anchors on: the first Monday on/after the
// start date (mirrors ``recurrence.first_cycle_monday`` on the backend).
// Only meaningful for a multi-week cycle with a start date set.
const cycleStartsOn = computed<string | null>(() => {
  if (periodWeeks.value <= 1 || !startsOn.value) return null;
  const s = startsOn.value;
  const pyWeekday = (s.getDay() + 6) % 7; // JS Sun=0 -> Python Mon=0
  const monday = new Date(s.getFullYear(), s.getMonth(), s.getDate() + ((7 - pyWeekday) % 7));
  return `${String(monday.getDate()).padStart(2, "0")}-${String(monday.getMonth() + 1).padStart(2, "0")}-${monday.getFullYear()}`;
});

// Shrinking k drops now-out-of-range cycle slots, warning which chores
// lost days (the server clamps too — this keeps the UI honest).
watch(periodWeeks, (next, prev) => {
  if (next >= prev) return;
  const hi = 7 * next;
  const affected: string[] = [];
  for (const c of chores.value) {
    const kept = c.cycle_slots.filter((s) => s < hi);
    if (kept.length !== c.cycle_slots.length) {
      affected.push(c.name || t("chores.edit.untitledChore"));
      c.cycle_slots = kept;
    }
  }
  if (affected.length) {
    toasts.warn(t("chores.edit.slotsCleared", { names: affected.join(", ") }));
  }
});

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

// The data watch is ``immediate`` and can fire synchronously during setup
// when the roster is already in the Query cache (warm navigation). The draft
// helpers below aren't initialised yet at that point, so gate the draft
// restore on this flag and run it once explicitly after they're defined.
let draftReady = false;

watch(
  () => rosterQuery?.data.value,
  (existing) => {
    if (!existing) return;
    nameNl.value = existing.name_nl ?? "";
    nameEn.value = existing.name_en ?? "";
    descNl.value = existing.description_nl ?? "";
    descEn.value = existing.description_en ?? "";
    imageUrl.value = existing.image_url ?? null;
    imageArtistInstagram.value = existing.image_artist_instagram ?? "";
    rosterLocale.value = existing.locale;
    chapterId.value = existing.chapter_id;
    periodWeeks.value = existing.period_weeks;
    startsOn.value = parseDate(existing.starts_on);
    endsOn.value = parseDate(existing.ends_on);
    reminderEnabled.value = existing.reminder_enabled;
    reminderDaysBefore.value = existing.reminder_days_before;
    commitHorizonDays.value = existing.commit_horizon_days;
    chores.value = (existing.chores ?? []).map((c) => ({
      id: c.id,
      name: c.name,
      description: c.description ?? null,
      cycle_slots: [...c.cycle_slots],
      people_per_shift: c.people_per_shift,
      emoji: c.emoji ?? DEFAULT_CHORE_EMOJI,
    }));
    if (draftReady) restoreDraftOnce();
  },
  { immediate: true },
);

// --- Draft persistence (dates stored as ISO strings) ---------------
const draftKey = computed(() => `chore-edit-draft:${props.rosterId ?? "new"}`);

interface RosterEditDraft {
  nameNl: string;
  nameEn: string;
  descNl: string;
  descEn: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  rosterLocale: "nl" | "en";
  periodWeeks: number;
  startsOn: string | null;
  endsOn: string | null;
  reminderEnabled: boolean;
  reminderDaysBefore: number;
  commitHorizonDays: number;
  chores: ChoreDraft[];
}

function snapshot(): RosterEditDraft {
  return {
    nameNl: nameNl.value,
    nameEn: nameEn.value,
    descNl: descNl.value,
    descEn: descEn.value,
    imageArtistInstagram: imageArtistInstagram.value,
    chapterId: chapterId.value,
    rosterLocale: rosterLocale.value,
    periodWeeks: periodWeeks.value,
    startsOn: isoDate(startsOn.value),
    endsOn: isoDate(endsOn.value),
    reminderEnabled: reminderEnabled.value,
    reminderDaysBefore: reminderDaysBefore.value,
    commitHorizonDays: commitHorizonDays.value,
    chores: chores.value,
  };
}

function applyDraft(d: RosterEditDraft): void {
  nameNl.value = d.nameNl ?? "";
  nameEn.value = d.nameEn ?? "";
  descNl.value = d.descNl ?? "";
  descEn.value = d.descEn ?? "";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
  chapterId.value = d.chapterId ?? null;
  rosterLocale.value = d.rosterLocale ?? "nl";
  periodWeeks.value = d.periodWeeks ?? 1;
  startsOn.value = parseDate(d.startsOn);
  endsOn.value = parseDate(d.endsOn);
  reminderEnabled.value = d.reminderEnabled ?? true;
  reminderDaysBefore.value = d.reminderDaysBefore ?? 1;
  commitHorizonDays.value = d.commitHorizonDays ?? 21;
  chores.value = (d.chores ?? []).map((c) => ({
    ...c,
    cycle_slots: [...(c.cycle_slots ?? [])],
    emoji: c.emoji ?? DEFAULT_CHORE_EMOJI,
  }));
}

const { loadDraft, clearDraft } = useFormDraft<RosterEditDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [
    nameNl,
    nameEn,
    descNl,
    descEn,
    imageArtistInstagram,
    chapterId,
    rosterLocale,
    periodWeeks,
    startsOn,
    endsOn,
    reminderEnabled,
    reminderDaysBefore,
    commitHorizonDays,
    chores,
  ],
});

let draftRestored = false;
function restoreDraftOnce(): void {
  if (draftRestored) return;
  draftRestored = true;
  const draft = loadDraft();
  if (draft) applyDraft(draft);
}

// The draft helpers exist now — apply any value the immediate watch above
// already loaded from a warm cache (it skipped the restore back then).
draftReady = true;
if (rosterQuery?.data.value) restoreDraftOnce();

// --- Chore list helpers --------------------------------------------
function addChore(): void {
  choreListState.add({
    id: null,
    name: "",
    description: null,
    cycle_slots: [],
    people_per_shift: 1,
    // Start a new chore on an emoji no existing chore already uses.
    emoji: firstUnusedEmoji(chores.value.map((c) => c.emoji)),
  });
}
function removeChore(index: number): void {
  choreListState.removeAt(index);
}
function moveChore(index: number, delta: -1 | 1): void {
  choreListState.move(index, delta);
}
function setChore(index: number, next: ChoreDraft): void {
  const prev = chores.value[index];
  // Keep emojis unique: picking one another chore already uses swaps them,
  // handing that chore this chore's previous emoji.
  if (next.emoji !== prev.emoji) {
    const clash = chores.value.findIndex((c, i) => i !== index && c.emoji === next.emoji);
    if (clash !== -1) {
      choreListState.replaceAt(clash, { ...chores.value[clash], emoji: prev.emoji });
    }
  }
  choreListState.replaceAt(index, next);
}


// --- Cancel / submit -----------------------------------------------
function cancel(): void {
  clearDraft();
  if (cancelStart()) return;
  if (isEdit.value && props.rosterId) {
    void router.push(`/chores/${props.rosterId}/details`);
  } else {
    void router.push("/chores");
  }
}

async function submit() {
  // The backend requires the title in the primary language (``rosterLocale``);
  // the other language is an optional translation.
  const primaryName = (rosterLocale.value === "en" ? nameEn.value : nameNl.value).trim();
  if (!primaryName) {
    toasts.warn(t("chores.edit.fillName"));
    return;
  }
  if (hasChapters.value && !chapterId.value) {
    toasts.warn(t("chores.edit.fillChapter"));
    return;
  }
  if (startActive.value && !validateStartEmail()) return;
  if (!startsOn.value) {
    toasts.warn(t("chores.edit.fillStartsOn"));
    return;
  }
  if (chores.value.some((c) => !c.name.trim())) {
    toasts.warn(t("chores.edit.fillChoreName"));
    return;
  }
  submitting.value = true;
  try {
    const wirePayload: RosterCreate | RosterUpdate = {
      chapter_id: chapterFor(chapterId.value),
      name_nl: nameNl.value.trim() || null,
      name_en: nameEn.value.trim() || null,
      description_nl: descNl.value.trim() || null,
      description_en: descEn.value.trim() || null,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
      locale: rosterLocale.value,
      location: null,
      latitude: null,
      longitude: null,
      period_weeks: periodWeeks.value,
      starts_on: isoDate(startsOn.value) as string,
      ends_on: isoDate(endsOn.value),
      reminder_enabled: reminderEnabled.value,
      reminder_days_before: reminderDaysBefore.value,
      commit_horizon_days: commitHorizonDays.value,
      chores: chores.value.map(
        (c): ChoreIn => ({
          id: c.id,
          name: c.name.trim(),
          description: c.description,
          cycle_slots: c.cycle_slots,
          people_per_shift: c.people_per_shift,
          emoji: c.emoji,
        }),
      ),
    };
    if (startActive.value) {
      // No session: the public link the response carries is the whole
      // result, and there is no details page to land on. A refusal has
      // already been explained; the draft stays so it can be retried.
      if (await submitStart(wirePayload)) clearDraft();
      return;
    }
    const result =
      isEdit.value && props.rosterId
        ? await updateMutation.mutateAsync({ id: props.rosterId, payload: wirePayload })
        : await createMutation.mutateAsync(wirePayload);
    await imageField.value?.flushPendingUpload(result.id);
    clearDraft();
    void router.push(`/chores/${result.id}/details`);
  } catch {
    toasts.error(t("chores.edit.saveFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <template v-if="notFound">
    <AppHeader />
    <div class="container-wide stack">
      <AppCard>
        <h2>{{ t("chores.edit.notFoundTitle") }}</h2>
        <p class="muted">{{ t("chores.edit.notFoundBody") }}</p>
        <router-link to="/chores" class="back-link">{{ t("chores.edit.backToList") }}</router-link>
      </AppCard>
    </div>
  </template>

  <template v-else-if="otherError">
    <AppHeader />
    <div class="container-wide stack">
      <AppCard>
        <p>{{ t("chores.edit.loadFailed") }}</p>
      </AppCard>
    </div>
  </template>

  <StartedPanel v-else-if="started" :started="started" :email="startEmail" />

  <FormPageShell
    v-else
    :title="isEdit ? t('chores.edit.editTitle') : t('chores.edit.newTitle')"
    :submit-label="isEdit ? t('chores.edit.save') : t('chores.edit.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
    <!-- Basics -->
    <section class="form-section">
      <StartAccountField v-if="startActive" v-model="startEmail" />
      <InputText
        v-model="title"
        :placeholder="titleFallback || t('chores.edit.namePlaceholder')"
        fluid
      />
      <RichTextField
        v-model="body"
        :placeholder="t('chores.edit.descriptionPlaceholder')"
        :fallback-html="bodyFallback || null"
      />
      <Select
        v-if="hasChapters"
        v-model="chapterId"
        :options="userChapterOptions"
        option-label="name"
        option-value="id"
        :placeholder="t('chores.edit.chapterPlaceholder')"
        :disabled="userChapterOptions.length === 1 && chapterId !== null"
        fluid
      />
    </section>

    <!-- Uploading writes to the row it belongs to, which takes a
         session the visitor does not have yet. -->
    <ImageField
      v-if="!startActive"
      ref="imageField"
      resource="chores"
      :entity-id="props.rosterId ?? null"
      v-model:image-url="imageUrl"
      v-model:artist="imageArtistInstagram"
    />

    <!-- Recurrence + run window -->
    <section class="form-section">
      <h2 class="section-heading">{{ t("chores.edit.recurrenceHeading") }}</h2>
      <p class="muted section-explainer">{{ t("chores.edit.recurrenceExplainer") }}</p>

      <div class="stepper-row">
        <NumberStepper v-model="periodWeeks" :min="1" :max="8" :aria-label="t('chores.edit.periodWeeks')" />
        <span v-if="cycleStartsOn" class="muted">
          {{ t("chores.edit.cycleStartsOn", { date: cycleStartsOn }) }}
        </span>
      </div>

      <div class="date-row">
        <div class="field">
          <DatePicker
            v-model="startsOn"
            date-format="dd-mm-yy"
            :placeholder="t('chores.edit.startDatePlaceholder')"
            fluid
          />
        </div>
        <div class="field">
          <DatePicker
            v-model="endsOn"
            date-format="dd-mm-yy"
            show-button-bar
            :placeholder="t('chores.edit.endsOnPlaceholder')"
            fluid
          />
        </div>
      </div>

      <details class="advanced">
        <summary>{{ t("chores.edit.advanced") }}</summary>
        <div class="field">
          <p class="muted section-explainer">{{ t("chores.edit.commitHorizonHint") }}</p>
          <NumberStepper
            v-model="commitHorizonDays"
            :min="reminderEnabled ? reminderDaysBefore : 1"
            :max="365"
            :aria-label="t('chores.edit.commitHorizonDays')"
          />
        </div>
      </details>
    </section>

    <!-- Chores -->
    <section class="form-section">
      <h2 class="section-heading">{{ t("chores.edit.choresHeading") }}</h2>
      <p class="muted section-explainer">{{ t("chores.edit.choresExplainer") }}</p>

      <div v-if="chores.length === 0" class="empty muted">
        {{ t("chores.edit.noChoresYet") }}
      </div>

      <div class="chores-stack">
        <ChoreEditor
          v-for="(c, idx) in chores"
          :key="c.id ?? `new-${idx}`"
          :model-value="c"
          :period-weeks="periodWeeks"
          :can-move-up="idx > 0"
          :can-move-down="idx < chores.length - 1"
          @update:model-value="(next) => setChore(idx, next)"
          @delete="removeChore(idx)"
          @move-up="moveChore(idx, -1)"
          @move-down="moveChore(idx, 1)"
        />
      </div>

      <Button
        type="button"
        :label="t('chores.edit.addChore')"
        icon="pi pi-plus"
        severity="secondary"
        @click="addChore"
      />
    </section>

    <!-- Reminders -->
    <section class="form-section">
      <label class="toggle-row" for="reminderToggle">
        <ToggleSwitch v-model="reminderEnabled" inputId="reminderToggle" />
        <h2 class="section-heading">{{ t("chores.edit.reminderEnabled") }}</h2>
      </label>
      <p class="muted section-explainer">{{ t("chores.edit.remindersExplainer") }}</p>

      <div v-if="reminderEnabled" class="field">
        <span class="field-label">{{ t("chores.edit.reminderDaysBefore") }}</span>
        <NumberStepper
          v-model="reminderDaysBefore"
          :min="0"
          :max="14"
          :aria-label="t('chores.edit.reminderDaysBefore')"
        />
      </div>
    </section>

    <!-- Language -->
    <section class="form-section">
      <h2 class="section-heading">{{ t("chores.edit.languageHeading") }}</h2>
      <p class="muted section-explainer">{{ t("chores.edit.languageExplainer") }}</p>
      <Select
        v-model="rosterLocale"
        :options="localeOptions"
        option-label="label"
        option-value="value"
        fluid
      />
    </section>
  </FormPageShell>
</template>

<style scoped>
/* Shared form chrome (.form-section, .section-heading, .section-explainer,
 * .toggle-row, .field, .field-label) lives in
 * ``src/assets/forms.css``. Only chore-specific rules stay here. */
.stepper-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.date-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}
.date-row .field {
  /* min-width: 0 so both fields shrink to the equal flex-basis instead of
   * being sized by their (unequal-length) placeholder text. */
  flex: 1 1 12rem;
  min-width: 0;
}
.field-error {
  margin: 0;
  color: var(--brand-red);
  font-size: 0.8125rem;
}
.chores-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.advanced > summary {
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--brand-text-muted);
  width: fit-content;
}
.advanced[open] > summary {
  margin-bottom: 0.5rem;
}
</style>
