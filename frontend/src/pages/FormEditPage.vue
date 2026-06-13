<script setup lang="ts">
import Button from "primevue/button";
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
import QuestionEditor, { type QuestionDraft } from "@/components/QuestionEditor.vue";
import { ApiError } from "@/api/client";
import { chapterList, useChapters } from "@/composables/useChapters";
import { useFormDraft } from "@/composables/useFormDraft";
import {
  type FormCreate,
  type FormQuestionIn,
  type FormUpdate,
  useCreateForm,
  useForm,
  useUpdateForm,
} from "@/composables/useForms";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ formId?: string }>();

const { t, locale } = useI18n();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();
const chaptersQuery = useChapters();
const chapters = chapterList(chaptersQuery);
const auth = useAuthStore();
const createMutation = useCreateForm();
const updateMutation = useUpdateForm();

const isEdit = computed(() => Boolean(props.formId));

// Chapter assignment. Same pattern as EventFormPage: pre-fill on
// create from ``?chapter=`` if it matches a live membership; if
// the user has exactly one chapter, lock to it; otherwise leave
// null and force a pick.
const chapterId = ref<string | null>(null);
const userChapterOptions = computed(() => {
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return chapters.value.filter((c) => memberIds.has(c.id));
});

const name = ref("");
const description = ref("");
const imageUrl = ref<string | null>(null);
const imageArtistInstagram = ref("");
const formLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
const questions = ref<QuestionDraft[]>([]);
const submitting = ref(false);

// Edit-mode hydration. ``useForm`` caches per-form-id so we only
// pay one round-trip even when navigating back through the list.
const existingQuery = computed(() => (props.formId ? props.formId : ""));
const formQuery = isEdit.value ? useForm(existingQuery) : null;

// Edit-mode error states. A bad / deleted form id used to leave
// the page stuck on a half-rendered form-shell skeleton; surface
// it as a not-found card with a back-link instead.
const notFound = computed(
  () =>
    isEdit.value &&
    formQuery?.error.value instanceof ApiError &&
    formQuery.error.value.status === 404,
);
const otherError = computed(
  () => isEdit.value && formQuery?.error.value && !notFound.value,
);

onMounted(() => {
  if (isEdit.value) return;
  // Create-mode chapter prefill.
  const queryChapter = (route.query.chapter as string | undefined) ?? null;
  const memberIds = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (queryChapter && memberIds.has(queryChapter)) {
    chapterId.value = queryChapter;
  } else if (auth.user?.chapters?.length === 1) {
    chapterId.value = auth.user.chapters[0].id;
  }
  // Restore the draft last so it wins over the chapter prefill.
  restoreDraftOnce();
});

// Edit-mode: copy the existing form into the local refs once the
// fetch lands. ``immediate`` so the snapshot also runs if the
// cache already had the row (e.g. arriving from the details page).
watch(
  () => formQuery?.data.value,
  (existing) => {
    if (!existing) return;
    name.value = existing.name;
    description.value = existing.description ?? "";
    imageUrl.value = existing.image_url ?? null;
    imageArtistInstagram.value = existing.image_artist_instagram ?? "";
    formLocale.value = existing.locale;
    chapterId.value = existing.chapter_id;
    questions.value = (existing.questions ?? []).map((q) => ({
      id: q.id,
      kind: q.kind as QuestionDraft["kind"],
      prompt: q.prompt,
      required: q.required,
      options: [...(q.options ?? [])],
      low_label: q.low_label ?? null,
      high_label: q.high_label ?? null,
    }));
    // Restore the mid-edit draft after server hydration so the
    // user's unsaved edits win over the stored form.
    restoreDraftOnce();
  },
  { immediate: true },
);

// --- Draft persistence ---------------------------------------------
// Mirrors EventFormPage: mid-edit state survives a refresh or
// accidental tab close. Keyed by form id (``new`` for create) so two
// tabs don't clobber each other. Cleared on successful save + cancel.
const draftKey = computed(() => `form-edit-draft:${props.formId ?? "new"}`);

interface FormEditDraft {
  name: string;
  description: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  formLocale: "nl" | "en";
  questions: QuestionDraft[];
}

function snapshot(): FormEditDraft {
  return {
    name: name.value,
    description: description.value,
    imageArtistInstagram: imageArtistInstagram.value,
    chapterId: chapterId.value,
    formLocale: formLocale.value,
    questions: questions.value,
  };
}

function applyDraft(d: FormEditDraft): void {
  name.value = d.name;
  description.value = d.description ?? "";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
  chapterId.value = d.chapterId ?? null;
  formLocale.value = d.formLocale ?? "nl";
  questions.value = (d.questions ?? []).map((q) => ({ ...q, options: [...(q.options ?? [])] }));
}

const { loadDraft, clearDraft } = useFormDraft<FormEditDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [name, description, imageArtistInstagram, chapterId, formLocale, questions],
});

// Restore at most once — the edit-mode hydration watch can fire more
// than once, but the draft should only ever override the first
// (initial) hydration, never re-clobber later user edits.
let draftRestored = false;
function restoreDraftOnce(): void {
  if (draftRestored) return;
  draftRestored = true;
  const draft = loadDraft();
  if (draft) applyDraft(draft);
}

// --- Question list helpers -----------------------------------------

function addQuestion(): void {
  questions.value.push({
    id: null,
    kind: "rating",
    prompt: "",
    required: true,
    options: [],
    low_label: null,
    high_label: null,
  });
}

function removeQuestion(index: number): void {
  questions.value.splice(index, 1);
}

function moveQuestion(index: number, delta: -1 | 1): void {
  const target = index + delta;
  if (target < 0 || target >= questions.value.length) return;
  const arr = questions.value;
  [arr[index], arr[target]] = [arr[target], arr[index]];
}

function setQuestion(index: number, next: QuestionDraft): void {
  questions.value[index] = next;
}

// --- Cancel / submit -----------------------------------------------

function cancel(): void {
  clearDraft();
  if (isEdit.value && props.formId) {
    void router.push(`/forms/${props.formId}/details`);
  } else {
    void router.push("/forms");
  }
}

async function submit() {
  const trimmedName = name.value.trim();
  if (!trimmedName) {
    toasts.warn(t("forms.edit.fillName"));
    return;
  }
  if (!chapterId.value) {
    toasts.warn(t("forms.edit.fillChapter"));
    return;
  }
  // Backend validates choice-options length etc.; surface a
  // localised generic on submit failure rather than raw 400
  // detail.
  submitting.value = true;
  try {
    const wirePayload: FormCreate | FormUpdate = {
      chapter_id: chapterId.value,
      name: trimmedName,
      description: description.value.trim() || null,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
      locale: formLocale.value,
      questions: questions.value.map(
        (q): FormQuestionIn => ({
          id: q.id,
          kind: q.kind,
          prompt: q.prompt,
          required: q.required,
          options: q.options,
          low_label: q.low_label,
          high_label: q.high_label,
        }),
      ),
    };
    const result =
      isEdit.value && props.formId
        ? await updateMutation.mutateAsync({ formId: props.formId, payload: wirePayload })
        : await createMutation.mutateAsync(wirePayload);
    clearDraft();
    void router.push(`/forms/${result.id}/details`);
  } catch {
    toasts.error(t("forms.edit.saveFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <!-- 404 / generic error short-circuits — rendered with the bare
       header + container instead of the form shell, because there's
       no form to save and the Save/Cancel footer would be
       misleading. -->
  <template v-if="notFound">
    <AppHeader />
    <div class="container stack">
      <AppCard>
        <h2>{{ t("forms.edit.notFoundTitle") }}</h2>
        <p class="muted">{{ t("forms.edit.notFoundBody") }}</p>
        <router-link to="/forms" class="back-link">{{ t("forms.edit.backToList") }}</router-link>
      </AppCard>
    </div>
  </template>

  <template v-else-if="otherError">
    <AppHeader />
    <div class="container stack">
      <AppCard>
        <p>{{ t("forms.edit.loadFailed") }}</p>
      </AppCard>
    </div>
  </template>

  <FormPageShell
    v-else
    :title="isEdit ? t('forms.edit.editTitle') : t('forms.edit.newTitle')"
    :submit-label="isEdit ? t('forms.edit.save') : t('forms.edit.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
    <section class="form-section">
      <InputText v-model="name" :placeholder="t('forms.edit.namePlaceholder')" fluid />
      <Textarea
        v-model="description"
        :placeholder="t('forms.edit.descriptionPlaceholder')"
        rows="2"
        auto-resize
        fluid
      />
      <Select
        v-model="chapterId"
        :options="userChapterOptions"
        option-label="name"
        option-value="id"
        :placeholder="t('forms.edit.chapterPlaceholder')"
        :disabled="userChapterOptions.length === 1 && chapterId !== null"
        fluid
      />
    </section>

    <ImageField
      resource="forms"
      :entity-id="props.formId ?? null"
      v-model:image-url="imageUrl"
      v-model:artist="imageArtistInstagram"
    />

    <section class="form-section">
      <h2 class="section-heading">{{ t("forms.edit.questionsHeading") }}</h2>
      <p class="muted section-explainer">{{ t("forms.edit.questionsExplainer") }}</p>

      <div v-if="questions.length === 0" class="empty muted">
        {{ t("forms.edit.noQuestionsYet") }}
      </div>

      <div class="questions-stack">
        <QuestionEditor
          v-for="(q, idx) in questions"
          :key="q.id ?? `new-${idx}`"
          :model-value="q"
          :can-move-up="idx > 0"
          :can-move-down="idx < questions.length - 1"
          @update:model-value="(next) => setQuestion(idx, next)"
          @delete="removeQuestion(idx)"
          @move-up="moveQuestion(idx, -1)"
          @move-down="moveQuestion(idx, 1)"
        />
      </div>

      <Button
        type="button"
        :label="t('forms.edit.addQuestion')"
        icon="pi pi-plus"
        severity="secondary"
        @click="addQuestion"
      />
    </section>

    <section class="form-section">
      <h2 class="section-heading">{{ t("forms.edit.localeHeading") }}</h2>
      <p class="muted section-explainer">{{ t("forms.edit.localeExplainer") }}</p>
      <Select
        v-model="formLocale"
        :options="[
          { value: 'nl', label: t('forms.edit.localeNl') },
          { value: 'en', label: t('forms.edit.localeEn') },
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
.questions-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
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
