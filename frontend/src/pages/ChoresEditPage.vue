<script setup lang="ts">
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import Textarea from "primevue/textarea";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import ChoreEditor, { type ChoreDraft } from "@/components/ChoreEditor.vue";
import FormPageShell from "@/components/FormPageShell.vue";
import ImageField from "@/components/ImageField.vue";
import NumberStepper from "@/components/NumberStepper.vue";
import { ApiError } from "@/api/client";
import type { ChoreIn, RosterCreate, RosterUpdate } from "@/api/types";
import { chapterList, useChapters } from "@/composables/useChapters";
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
const chaptersQuery = useChapters();
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

const name = ref("");
const description = ref("");
const imageUrl = ref<string | null>(null);
const imageArtistInstagram = ref("");
const imageField = ref<InstanceType<typeof ImageField> | null>(null);
const rosterLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
const periodWeeks = ref(1);
const anchorMonday = ref<Date | null>(null);
const startsOn = ref<Date | null>(null);
const endsOn = ref<Date | null>(null);
const reminderEnabled = ref(true);
const reminderDaysBefore = ref(1);
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

const anchorError = computed<string | null>(() => {
  if (periodWeeks.value <= 1) return null;
  if (!anchorMonday.value) return t("chores.edit.anchorRequired");
  if (anchorMonday.value.getDay() !== 1) return t("chores.edit.anchorNotMonday");
  return null;
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
  if (!startsOn.value) startsOn.value = new Date();
  const queryChapter = (route.query.chapter as string | undefined) ?? null;
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (queryChapter && memberIds.has(queryChapter)) {
    chapterId.value = queryChapter;
  } else if (auth.user?.chapters?.length === 1) {
    chapterId.value = auth.user.chapters[0].id;
  }
  restoreDraftOnce();
});

watch(
  () => rosterQuery?.data.value,
  (existing) => {
    if (!existing) return;
    name.value = existing.name;
    description.value = existing.description ?? "";
    imageUrl.value = existing.image_url ?? null;
    imageArtistInstagram.value = existing.image_artist_instagram ?? "";
    rosterLocale.value = existing.locale;
    chapterId.value = existing.chapter_id;
    periodWeeks.value = existing.period_weeks;
    anchorMonday.value = parseDate(existing.anchor_monday);
    startsOn.value = parseDate(existing.starts_on);
    endsOn.value = parseDate(existing.ends_on);
    reminderEnabled.value = existing.reminder_enabled;
    reminderDaysBefore.value = existing.reminder_days_before;
    chores.value = (existing.chores ?? []).map((c) => ({
      id: c.id,
      name: c.name,
      description: c.description ?? null,
      cycle_slots: [...c.cycle_slots],
      people_per_shift: c.people_per_shift,
      emoji: c.emoji ?? null,
    }));
    restoreDraftOnce();
  },
  { immediate: true },
);

// --- Draft persistence (dates stored as ISO strings) ---------------
const draftKey = computed(() => `chore-edit-draft:${props.rosterId ?? "new"}`);

interface RosterEditDraft {
  name: string;
  description: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  rosterLocale: "nl" | "en";
  periodWeeks: number;
  anchorMonday: string | null;
  startsOn: string | null;
  endsOn: string | null;
  reminderEnabled: boolean;
  reminderDaysBefore: number;
  chores: ChoreDraft[];
}

function snapshot(): RosterEditDraft {
  return {
    name: name.value,
    description: description.value,
    imageArtistInstagram: imageArtistInstagram.value,
    chapterId: chapterId.value,
    rosterLocale: rosterLocale.value,
    periodWeeks: periodWeeks.value,
    anchorMonday: isoDate(anchorMonday.value),
    startsOn: isoDate(startsOn.value),
    endsOn: isoDate(endsOn.value),
    reminderEnabled: reminderEnabled.value,
    reminderDaysBefore: reminderDaysBefore.value,
    chores: chores.value,
  };
}

function applyDraft(d: RosterEditDraft): void {
  name.value = d.name;
  description.value = d.description ?? "";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
  chapterId.value = d.chapterId ?? null;
  rosterLocale.value = d.rosterLocale ?? "nl";
  periodWeeks.value = d.periodWeeks ?? 1;
  anchorMonday.value = parseDate(d.anchorMonday);
  startsOn.value = parseDate(d.startsOn) ?? new Date();
  endsOn.value = parseDate(d.endsOn);
  reminderEnabled.value = d.reminderEnabled ?? true;
  reminderDaysBefore.value = d.reminderDaysBefore ?? 1;
  chores.value = (d.chores ?? []).map((c) => ({ ...c, cycle_slots: [...(c.cycle_slots ?? [])] }));
}

const { loadDraft, clearDraft } = useFormDraft<RosterEditDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [
    name,
    description,
    imageArtistInstagram,
    chapterId,
    rosterLocale,
    periodWeeks,
    anchorMonday,
    startsOn,
    endsOn,
    reminderEnabled,
    reminderDaysBefore,
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

// --- Chore list helpers --------------------------------------------
function addChore(): void {
  choreListState.add({
    id: null,
    name: "",
    description: null,
    cycle_slots: [],
    people_per_shift: 1,
    emoji: null,
  });
}
function removeChore(index: number): void {
  choreListState.removeAt(index);
}
function moveChore(index: number, delta: -1 | 1): void {
  choreListState.move(index, delta);
}
function setChore(index: number, next: ChoreDraft): void {
  choreListState.replaceAt(index, next);
}

// --- Cancel / submit -----------------------------------------------
function cancel(): void {
  clearDraft();
  if (isEdit.value && props.rosterId) {
    void router.push(`/chores/${props.rosterId}/details`);
  } else {
    void router.push("/chores");
  }
}

async function submit() {
  const trimmedName = name.value.trim();
  if (!trimmedName) {
    toasts.warn(t("chores.edit.fillName"));
    return;
  }
  if (!chapterId.value) {
    toasts.warn(t("chores.edit.fillChapter"));
    return;
  }
  if (!startsOn.value) {
    toasts.warn(t("chores.edit.fillStartsOn"));
    return;
  }
  if (anchorError.value) {
    toasts.warn(anchorError.value);
    return;
  }
  submitting.value = true;
  try {
    const wirePayload: RosterCreate | RosterUpdate = {
      chapter_id: chapterId.value,
      name: trimmedName,
      description: description.value.trim() || null,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
      locale: rosterLocale.value,
      location: null,
      latitude: null,
      longitude: null,
      period_weeks: periodWeeks.value,
      anchor_monday: periodWeeks.value > 1 ? isoDate(anchorMonday.value) : null,
      starts_on: isoDate(startsOn.value) as string,
      ends_on: isoDate(endsOn.value),
      reminder_enabled: reminderEnabled.value,
      reminder_days_before: reminderDaysBefore.value,
      chores: chores.value.map(
        (c): ChoreIn => ({
          id: c.id,
          name: c.name,
          description: c.description,
          cycle_slots: c.cycle_slots,
          people_per_shift: c.people_per_shift,
          emoji: c.emoji,
        }),
      ),
    };
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
    <div class="container stack">
      <AppCard>
        <h2>{{ t("chores.edit.notFoundTitle") }}</h2>
        <p class="muted">{{ t("chores.edit.notFoundBody") }}</p>
        <router-link to="/chores" class="back-link">{{ t("chores.edit.backToList") }}</router-link>
      </AppCard>
    </div>
  </template>

  <template v-else-if="otherError">
    <AppHeader />
    <div class="container stack">
      <AppCard>
        <p>{{ t("chores.edit.loadFailed") }}</p>
      </AppCard>
    </div>
  </template>

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
      <InputText v-model="name" :placeholder="t('chores.edit.namePlaceholder')" fluid />
      <Textarea
        v-model="description"
        :placeholder="t('chores.edit.descriptionPlaceholder')"
        rows="2"
        auto-resize
        fluid
      />
      <Select
        v-model="chapterId"
        :options="userChapterOptions"
        option-label="name"
        option-value="id"
        :placeholder="t('chores.edit.chapterPlaceholder')"
        :disabled="userChapterOptions.length === 1 && chapterId !== null"
        fluid
      />
    </section>

    <ImageField
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

      <div class="field">
        <span class="field-label">{{ t("chores.edit.periodWeeks") }}</span>
        <NumberStepper v-model="periodWeeks" :min="1" :max="8" :aria-label="t('chores.edit.periodWeeks')" />
      </div>

      <div v-if="periodWeeks > 1" class="field">
        <span class="field-label">{{ t("chores.edit.anchorMonday") }}</span>
        <DatePicker v-model="anchorMonday" date-format="dd-mm-yy" :placeholder="t('chores.edit.anchorMonday')" fluid />
        <p v-if="anchorError" class="field-error">{{ anchorError }}</p>
      </div>

      <div class="date-row">
        <div class="field">
          <span class="field-label">{{ t("chores.edit.startsOn") }}</span>
          <DatePicker v-model="startsOn" date-format="dd-mm-yy" :placeholder="t('chores.edit.startsOn')" fluid />
        </div>
        <div class="field">
          <span class="field-label">{{ t("chores.edit.endsOn") }}</span>
          <DatePicker
            v-model="endsOn"
            date-format="dd-mm-yy"
            show-button-bar
            :placeholder="t('chores.edit.endsOnPlaceholder')"
            fluid
          />
        </div>
      </div>
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
      <h2 class="section-heading">{{ t("chores.edit.remindersHeading") }}</h2>
      <p class="muted section-explainer">{{ t("chores.edit.remindersExplainer") }}</p>

      <label class="toggle-row" for="reminderToggle">
        <ToggleSwitch v-model="reminderEnabled" inputId="reminderToggle" />
        <strong>{{ t("chores.edit.reminderEnabled") }}</strong>
      </label>

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
 * .toggle-row, .toggle-help, .field, .field-label) lives in
 * ``src/assets/forms.css``. Only chore-specific rules stay here. */
.date-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}
.date-row .field {
  flex: 1 1 12rem;
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
.empty {
  padding: 0.75rem;
  border: 1px dashed var(--brand-border);
  border-radius: 8px;
  text-align: center;
}
</style>
