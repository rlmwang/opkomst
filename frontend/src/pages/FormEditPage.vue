<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import FormPageShell from "@/components/FormPageShell.vue";
import ImageField from "@/components/ImageField.vue";
import QuestionEditor, { type QuestionDraft } from "@/components/QuestionEditor.vue";
import RichTextField from "@/components/RichTextField.vue";
import { ApiError } from "@/api/client";
import StartAccountField from "@/components/StartAccountField.vue";
import StartedPanel from "@/components/StartedPanel.vue";
import { chapterList, useChapters } from "@/composables/useChapters";
import { useStartMode } from "@/composables/useStartMode";
import { useBilingualField } from "@/composables/useBilingualField";
import { useFormDraft } from "@/composables/useFormDraft";
import { useOrderedList } from "@/composables/useOrderedList";
import { type FormCreate, type FormQuestionIn, type FormUpdate, useFormsApi } from "@/composables/useForms";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ formId?: string }>();

const { t, te, locale } = useI18n();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();
// The root's front door: see ``useStartMode``.
// One page, two products (``docs/design-quizzes.md``). The route says
// which; everything below that reads the same, because a quiz is a
// questionnaire with an answer key.
const api = useFormsApi();
const isQuiz = computed(() => api.resource === "quizzes");
/** ``quizzes.<key>`` when there is one, ``forms.<key>`` otherwise. The
 *  two products share every string that is not about scoring. */
const L = (key: string, params?: Record<string, unknown>) => {
  const full = isQuiz.value && te(`quizzes.${key}`) ? `quizzes.${key}` : `forms.${key}`;
  return params ? t(full, params) : t(full);
};

const {
  active: startActive,
  hasChapters,
  email: startEmail,
  started,
  validate: validateStartEmail,
  submit: submitStart,
  chapterFor,
  cancel: cancelStart,
} = useStartMode(api.resource === "quizzes" ? "quiz" : "form");
const chaptersQuery = useChapters({ enabled: hasChapters });
const chapters = chapterList(chaptersQuery);
const auth = useAuthStore();
const createMutation = api.useCreate();
const updateMutation = api.useUpdate();

const isEdit = computed(() => Boolean(props.formId));

/* Quiz only: whether the result screen names the right answers. An
 * organiser running the same quiz twice in one evening turns it off. */
const revealAnswers = ref(true);

// Chapter assignment. Same pattern as EventFormPage: pre-fill on
// create from ``?chapter=`` if it matches a live membership; if
// the user has exactly one chapter, lock to it; otherwise leave
// null and force a pick.
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
const formLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
const questionList = useOrderedList<QuestionDraft>();
const questions = questionList.items;
const submitting = ref(false);

// Edit-mode hydration. ``useForm`` caches per-form-id so we only
// pay one round-trip even when navigating back through the list.
const existingQuery = computed(() => (props.formId ? props.formId : ""));
const formQuery = isEdit.value ? api.useSingle(existingQuery) : null;

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
// That warm-cache fire happens during setup, before the draft helpers
// below exist — so gate the draft restore on this flag and run it once
// explicitly afterwards.
let draftReady = false;
watch(
  () => formQuery?.data.value,
  (existing) => {
    if (!existing) return;
    nameNl.value = existing.name_nl ?? "";
    nameEn.value = existing.name_en ?? "";
    descNl.value = existing.description_nl ?? "";
    descEn.value = existing.description_en ?? "";
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
      min_value: q.min_value ?? null,
      max_value: q.max_value ?? null,
      step: q.step ?? null,
      points: q.points ?? 0,
      correct_int: q.correct_int ?? null,
      correct_text: q.correct_text ?? null,
      correct_choices: q.correct_choices ? [...q.correct_choices] : null,
      tolerance: q.tolerance ?? null,
    }));
    revealAnswers.value = existing.reveal_answers ?? true;
    // Restore the mid-edit draft after server hydration so the
    // user's unsaved edits win over the stored form.
    if (draftReady) restoreDraftOnce();
  },
  { immediate: true },
);

// --- Draft persistence ---------------------------------------------
// Mirrors EventFormPage: mid-edit state survives a refresh or
// accidental tab close. Keyed by form id (``new`` for create) so two
// tabs don't clobber each other. Cleared on successful save + cancel.
const draftKey = computed(() => `form-edit-draft:${props.formId ?? "new"}`);

interface FormEditDraft {
  nameNl: string;
  nameEn: string;
  descNl: string;
  descEn: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  formLocale: "nl" | "en";
  questions: QuestionDraft[];
}

function snapshot(): FormEditDraft {
  return {
    nameNl: nameNl.value,
    nameEn: nameEn.value,
    descNl: descNl.value,
    descEn: descEn.value,
    imageArtistInstagram: imageArtistInstagram.value,
    chapterId: chapterId.value,
    formLocale: formLocale.value,
    questions: questions.value,
  };
}

function applyDraft(d: FormEditDraft): void {
  nameNl.value = d.nameNl ?? "";
  nameEn.value = d.nameEn ?? "";
  descNl.value = d.descNl ?? "";
  descEn.value = d.descEn ?? "";
  imageArtistInstagram.value = d.imageArtistInstagram ?? "";
  chapterId.value = d.chapterId ?? null;
  formLocale.value = d.formLocale ?? "nl";
  questions.value = (d.questions ?? []).map((q) => ({ ...q, options: [...(q.options ?? [])] }));
}

const { loadDraft, clearDraft } = useFormDraft<FormEditDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [nameNl, nameEn, descNl, descEn, imageArtistInstagram, chapterId, formLocale, questions],
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

// The draft helpers exist now — apply any value the immediate watch above
// already loaded from a warm cache (it skipped the restore back then).
draftReady = true;
if (formQuery?.data.value) restoreDraftOnce();

/** The first thing wrong with the question list, in words, or null.
 *  Mirrors the rules in ``services/forms._validate_questions`` and
 *  ``services/quizzes.validate_keys``: the server is still the
 *  authority, this is so the answer arrives in Dutch and names the
 *  question. */
function firstQuestionProblem(): string | null {
  for (const [index, q] of questions.value.entries()) {
    const n = index + 1;
    if (!q.prompt.trim()) return L("edit.questionNeedsPrompt", { n });
    const choice = q.kind === "single_choice" || q.kind === "multi_choice";
    if (choice && q.options.length < 2) return L("edit.questionNeedsOptions", { n });
    if (!isQuiz.value || q.points <= 0) continue;
    if (choice && (q.correct_choices ?? []).length === 0) return L("edit.questionNeedsKey", { n });
    if (q.kind === "single_choice" && (q.correct_choices ?? []).length !== 1) {
      return L("edit.questionNeedsOneKey", { n });
    }
    if ((q.kind === "number" || q.kind === "rating") && q.correct_int === null) {
      return L("edit.questionNeedsKey", { n });
    }
  }
  return null;
}

// --- Question list helpers -----------------------------------------

function addQuestion(): void {
  questionList.add({
    id: null,
    kind: "rating",
    prompt: "",
    required: true,
    options: [],
    low_label: null,
    high_label: null,
    min_value: null,
    max_value: null,
    step: null,
    // A new quiz question is worth one point; a survey's is worth
    // nothing and the server drops it either way.
    points: isQuiz.value ? 1 : 0,
    correct_int: null,
    correct_text: null,
    correct_choices: null,
    tolerance: null,
  });
}

function removeQuestion(index: number): void {
  questionList.removeAt(index);
}

function moveQuestion(index: number, delta: -1 | 1): void {
  questionList.move(index, delta);
}

function setQuestion(index: number, next: QuestionDraft): void {
  questionList.replaceAt(index, next);
}

// --- Cancel / submit -----------------------------------------------

function cancel(): void {
  clearDraft();
  if (cancelStart()) return;
  if (isEdit.value && props.formId) {
    void router.push(`/${api.resource}/${props.formId}/details`);
  } else {
    void router.push(`/${api.resource}`);
  }
}

async function submit() {
  // Backend requires the title in the primary language (``formLocale``).
  const primaryName = (formLocale.value === "en" ? nameEn.value : nameNl.value).trim();
  // What the server refuses, checked here first and said with the
  // question's number in it. A 400 from the API is accurate and
  // English, and "saving failed" is neither: an organiser who left one
  // answer unmarked should be told which one.
  const problem = firstQuestionProblem();
  if (problem) {
    toasts.warn(problem);
    return;
  }
  if (!primaryName) {
    toasts.warn(L("edit.fillName"));
    return;
  }
  if (hasChapters.value && !chapterId.value) {
    toasts.warn(L("edit.fillChapter"));
    return;
  }
  if (startActive.value && !validateStartEmail()) return;
  // Backend validates choice-options length etc.; surface a
  // localised generic on submit failure rather than raw 400
  // detail.
  submitting.value = true;
  try {
    const wirePayload: FormCreate | FormUpdate = {
      chapter_id: chapterFor(chapterId.value),
      name_nl: nameNl.value.trim() || null,
      name_en: nameEn.value.trim() || null,
      description_nl: descNl.value.trim() || null,
      description_en: descEn.value.trim() || null,
      image_artist_instagram: imageArtistInstagram.value.trim() || null,
      locale: formLocale.value,
      reveal_answers: revealAnswers.value,
      questions: questions.value.map(
        (q): FormQuestionIn => ({
          id: q.id,
          kind: q.kind,
          prompt: q.prompt,
          required: q.required,
          options: q.options,
          low_label: q.low_label,
          high_label: q.high_label,
          min_value: q.min_value,
          max_value: q.max_value,
          step: q.step,
          points: q.points,
          correct_int: q.correct_int,
          correct_text: q.correct_text,
          correct_choices: q.correct_choices,
          tolerance: q.tolerance,
        }),
      ),
    };
    if (startActive.value) {
      // No session: no details page to land on, and the public link
      // the response carries is the whole result. A refusal has already
      // been explained; the draft stays so it can be retried.
      if (await submitStart(wirePayload)) clearDraft();
      return;
    }
    const result =
      isEdit.value && props.formId
        ? await updateMutation.mutateAsync({ id: props.formId, payload: wirePayload })
        : await createMutation.mutateAsync(wirePayload);
    // Upload a create-mode held image to the freshly-created row
    // (no-op in edit mode / when nothing was picked).
    await imageField.value?.flushPendingUpload(result.id);
    clearDraft();
    void router.push(`/${api.resource}/${result.id}/details`);
  } catch {
    toasts.error(L("edit.saveFailed"));
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
    <div class="container-wide stack">
      <AppCard>
        <h2>{{ L("edit.notFoundTitle") }}</h2>
        <p class="muted">{{ L("edit.notFoundBody") }}</p>
        <router-link :to="`/${api.resource}`" class="back-link">{{ L("edit.backToList") }}</router-link>
      </AppCard>
    </div>
  </template>

  <template v-else-if="otherError">
    <AppHeader />
    <div class="container-wide stack">
      <AppCard>
        <p>{{ L("edit.loadFailed") }}</p>
      </AppCard>
    </div>
  </template>

  <StartedPanel v-else-if="started" :started="started" :email="startEmail" />

  <FormPageShell
    v-else
    :title="isEdit ? L('edit.editTitle') : L('edit.newTitle')"
    :submit-label="isEdit ? t('forms.edit.save') : t('forms.edit.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
    <section class="form-section">
      <StartAccountField v-if="startActive" v-model="startEmail" />
      <InputText
        v-model="title"
        :placeholder="titleFallback || t('forms.edit.namePlaceholder')"
        fluid
      />
      <RichTextField
        v-model="body"
        :placeholder="t('forms.edit.descriptionPlaceholder')"
        :fallback-html="bodyFallback || null"
      />
      <Select
        v-if="hasChapters"
        v-model="chapterId"
        :options="userChapterOptions"
        option-label="name"
        option-value="id"
        :placeholder="t('forms.edit.chapterPlaceholder')"
        :disabled="userChapterOptions.length === 1 && chapterId !== null"
        fluid
      />
    </section>

    <!-- Uploading writes to the row it belongs to, which takes a
         session the visitor does not have yet. -->
    <ImageField
      v-if="!startActive"
      ref="imageField"
      resource="forms"
      :entity-id="props.formId ?? null"
      v-model:image-url="imageUrl"
      v-model:artist="imageArtistInstagram"
    />

    <section class="form-section">
      <h2 class="section-heading">{{ L("edit.questionsHeading") }}</h2>
      <p class="muted section-explainer">{{ L("edit.questionsExplainer") }}</p>

      <div v-if="questions.length === 0" class="empty muted">
        {{ L("edit.noQuestionsYet") }}
      </div>

      <div class="questions-stack">
        <QuestionEditor
          v-for="(q, idx) in questions"
          :scored="isQuiz"
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
        :label="L('edit.addQuestion')"
        icon="pi pi-plus"
        severity="secondary"
        @click="addQuestion"
      />
    </section>

    <!-- Quiz only. Under the questions because it is about what
         happens after they are answered. -->
    <section v-if="isQuiz" class="form-section">
      <label class="toggle-row" for="revealToggle">
        <ToggleSwitch v-model="revealAnswers" inputId="revealToggle" />
        <h2 class="section-heading">{{ t("quizzes.edit.revealHeading") }}</h2>
      </label>
      <p class="muted section-explainer">{{ t("quizzes.edit.revealExplainer") }}</p>
    </section>

    <section class="form-section">
      <h2 class="section-heading">{{ L("edit.localeHeading") }}</h2>
      <p class="muted section-explainer">{{ L("edit.localeExplainer") }}</p>
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
/* Shared form chrome (.form-section, .section-heading,
 * .section-explainer) lives in ``src/assets/forms.css``. */
.questions-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
