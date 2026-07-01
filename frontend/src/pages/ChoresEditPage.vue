<script setup lang="ts">
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
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
const anchorMonday = ref<string | null>(null);
const startsOn = ref<string>("");
const endsOn = ref<string | null>(null);
const reminderEnabled = ref(true);
const reminderDaysBefore = ref(1);
const choreListState = useOrderedList<ChoreDraft>();
const chores = choreListState.items;
const submitting = ref(false);

const existingQuery = computed(() => (props.rosterId ? props.rosterId : ""));
const rosterQuery = isEdit.value ? useRoster(existingQuery) : null;

const notFound = computed(
  () =>
    isEdit.value &&
    rosterQuery?.error.value instanceof ApiError &&
    rosterQuery.error.value.status === 404,
);
const otherError = computed(
  () => isEdit.value && rosterQuery?.error.value && !notFound.value,
);

/** Local-time weekday check so a "YYYY-MM-DD" string isn't shifted by
 * UTC parsing. Monday === 1 in ``Date.getDay()``. */
function isMonday(iso: string | null): boolean {
  if (!iso) return false;
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return false;
  return new Date(y, m - 1, d).getDay() === 1;
}

const anchorError = computed<string | null>(() => {
  if (periodWeeks.value <= 1) return null;
  if (!anchorMonday.value) return t("chores.edit.anchorRequired");
  if (!isMonday(anchorMonday.value)) return t("chores.edit.anchorNotMonday");
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

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

onMounted(() => {
  if (isEdit.value) return;
  if (!startsOn.value) startsOn.value = todayIso();
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
    anchorMonday.value = existing.anchor_monday ?? null;
    startsOn.value = existing.starts_on;
    endsOn.value = existing.ends_on ?? null;
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

// --- Draft persistence ---------------------------------------------
const draftKey = computed(() => `chore-edit-draft:${props.rosterId ?? "new"}`);

interface RosterEditDraft {
  name: string;
  description: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  rosterLocale: "nl" | "en";
  periodWeeks: number;
  anchorMonday: string | null;
  startsOn: string;
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
    anchorMonday: anchorMonday.value,
    startsOn: startsOn.value,
    endsOn: endsOn.value,
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
  anchorMonday.value = d.anchorMonday ?? null;
  startsOn.value = d.startsOn || todayIso();
  endsOn.value = d.endsOn ?? null;
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
      anchor_monday: periodWeeks.value > 1 ? anchorMonday.value : null,
      starts_on: startsOn.value,
      ends_on: endsOn.value || null,
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

    <!-- Recurrence controls (roster-level, above the chore list). -->
    <section class="form-section">
      <h2 class="section-heading">{{ t("chores.edit.recurrenceHeading") }}</h2>
      <p class="muted section-explainer">{{ t("chores.edit.recurrenceExplainer") }}</p>

      <label class="field-row">
        <span>{{ t("chores.edit.periodWeeks") }}</span>
        <InputNumber v-model="periodWeeks" :min="1" :max="8" show-buttons button-layout="horizontal" />
      </label>

      <label v-if="periodWeeks > 1" class="field-row">
        <span>{{ t("chores.edit.anchorMonday") }}</span>
        <input type="date" class="date-input" v-model="anchorMonday" />
      </label>
      <p v-if="anchorError" class="field-error">{{ anchorError }}</p>

      <div class="field-grid">
        <label class="field-row">
          <span>{{ t("chores.edit.startsOn") }}</span>
          <input type="date" class="date-input" v-model="startsOn" />
        </label>
        <label class="field-row">
          <span>{{ t("chores.edit.endsOn") }}</span>
          <input type="date" class="date-input" v-model="endsOn" />
        </label>
      </div>

      <label class="toggle-row">
        <ToggleSwitch v-model="reminderEnabled" />
        <span>{{ t("chores.edit.reminderEnabled") }}</span>
      </label>
      <label v-if="reminderEnabled" class="field-row">
        <span>{{ t("chores.edit.reminderDaysBefore") }}</span>
        <InputNumber v-model="reminderDaysBefore" :min="0" :max="14" show-buttons button-layout="horizontal" />
      </label>
    </section>

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
  </FormPageShell>
</template>

<style scoped>
.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.section-heading { margin: 0; }
.section-explainer { margin: 0; font-size: 0.875rem; }
.field-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.9375rem;
}
.field-row > span { min-width: 12rem; }
.field-grid {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.field-grid .field-row > span { min-width: 6rem; }
.toggle-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  align-self: flex-start;
}
.date-input {
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
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
.back-link { display: inline-block; margin-top: 0.5rem; }
</style>
