<script setup lang="ts">
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import Textarea from "primevue/textarea";
import { computed, onMounted, ref, watch } from "vue";
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

const name = ref("");
const description = ref("");
const imageUrl = ref<string | null>(null);
const imageArtistInstagram = ref("");
const imageField = ref<InstanceType<typeof ImageField> | null>(null);
const pollLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
// Candidate dates as ``Date`` objects (PrimeVue multiple-select).
const selectedDates = ref<Date[]>([]);
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
    selectedDates.value = (existing.dates ?? []).map((d) => fromISODate(d.on_date));
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
}

function snapshot(): DatepollDraft {
  return {
    name: name.value,
    description: description.value,
    imageArtistInstagram: imageArtistInstagram.value,
    chapterId: chapterId.value,
    pollLocale: pollLocale.value,
    dates: sortedISODates.value,
  };
}

function applyDraft(d: DatepollDraft): void {
  name.value = d.name;
  description.value = d.description ?? "";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
  chapterId.value = d.chapterId ?? null;
  pollLocale.value = d.pollLocale ?? "nl";
  selectedDates.value = (d.dates ?? []).map(fromISODate);
}

const { loadDraft, clearDraft } = useFormDraft<DatepollDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [name, description, imageArtistInstagram, chapterId, pollLocale, selectedDates],
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
    const wirePayload: DatepollCreate | DatepollUpdate = {
      chapter_id: chapterId.value,
      name: trimmedName,
      description: description.value.trim() || null,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
      locale: pollLocale.value,
      dates: sortedISODates.value.map((iso) => ({ on_date: iso })),
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
        <DatePicker v-model="selectedDates" selection-mode="multiple" inline :manual-input="false" />

        <p v-if="sortedISODates.length === 0" class="empty muted">
          {{ t("datepolls.edit.noDatesYet") }}
        </p>
        <div v-else class="chosen">
          <p class="muted chosen-count">{{ t("datepolls.edit.datesSelected", { n: sortedISODates.length }) }}</p>
          <ul class="chips">
            <li v-for="iso in sortedISODates" :key="iso">
              <button
                type="button"
                class="chip"
                :aria-label="`${t('datepolls.edit.removeDate')}: ${chipLabel(iso)}`"
                @click="removeDate(iso)"
              >
                <span>{{ chipLabel(iso) }}</span>
                <span class="x" aria-hidden="true">×</span>
              </button>
            </li>
          </ul>
        </div>
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
/* Calendar on top, the picked-dates summary below — a wrapping chip
 * row, not a vertical list, so a long selection grows in width-then-
 * wrap instead of pushing the Save/Cancel footer off-screen. */
.dates-stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: flex-start;
}
.chosen { width: 100%; min-width: 0; }
.chosen-count { margin: 0 0 0.5rem; font-size: 0.8125rem; }
/* Equal-width cells (``1fr`` columns, auto-filled) so the chips line
 * up into a neat grid instead of a ragged wrap; each chip fills its
 * cell. */
.chips {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
  gap: 0.375rem;
}
.chip {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  box-sizing: border-box;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem 0.25rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
  white-space: nowrap;
}
.chip:hover { border-color: var(--brand-red); }
.chip .x { color: var(--brand-text-muted); font-size: 1rem; line-height: 1; }
.chip:hover .x { color: var(--brand-red); }
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
