<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import AppInput from "@/components/AppInput.vue";
import SelectField from "@/components/SelectField.vue";
import AppToggle from "@/components/AppToggle.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import FormPageShell from "@/components/FormPageShell.vue";
import ImageField from "@/components/ImageField.vue";
import CompassAxesEditor from "@/components/CompassAxesEditor.vue";
import QuestionEditor, { type PoleOption, type QuestionDraft } from "@/components/QuestionEditor.vue";
import RichTextField from "@/components/RichTextField.vue";
import { ApiError } from "@/api/client";
import StartAccountField from "@/components/StartAccountField.vue";
import StartedPanel from "@/components/StartedPanel.vue";
import { chapterList, useChapters } from "@/composables/useChapters";
import { type StartKind, useStartMode } from "@/composables/useStartMode";
import { useBilingualField } from "@/composables/useBilingualField";
import { useFormDraft } from "@/composables/useFormDraft";
import { useOrderedList } from "@/composables/useOrderedList";
import { type FormCreate, type FormQuestionIn, type FormUpdate, useFormsApi } from "@/composables/useForms";
import type { CompassAxisIn, Pole } from "@/api/types";
import { useFormText } from "@/composables/useFormText";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ formId?: string }>();

const { t, locale } = useI18n();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();
// The root's front door: see ``useStartMode``.
// One page, three products (``docs/design-quizzes.md``,
// ``docs/design-kompas.md``). The route says which; everything below
// that reads the same, because a quiz is a questionnaire with an
// answer key and a kompas is one with a direction per answer.
const api = useFormsApi();
const { L, isQuiz: quizProduct, isCompass: compassProduct } = useFormText();
/** The create body's wire name at the root's front door, per product. */
const START_KIND: Record<string, StartKind> = { forms: "form", quizzes: "quiz", compasses: "compass" };
const isQuiz = computed(() => quizProduct);
const isCompass = computed(() => compassProduct);

const {
  active: startActive,
  hasChapters,
  email: startEmail,
  started,
  validate: validateStartEmail,
  submit: submitStart,
  chapterFor,
  cancel: cancelStart,
} = useStartMode(START_KIND[api.resource]);
const chaptersQuery = useChapters({ enabled: hasChapters });
const chapters = chapterList(chaptersQuery);
const auth = useAuthStore();
const createMutation = api.useCreate();
const updateMutation = api.useUpdate();

const isEdit = computed(() => Boolean(props.formId));

/** The four sides, labelled with what the organiser called them. Read
 *  live off the axes block above, so renaming an axis renames every
 *  select on the page. Before the axes are named they read "As X,
 *  kant 1", which is a placeholder the save then refuses. */
const poleOptions = computed<PoleOption[]>(() =>
  (["x", "y"] as const).flatMap((axis) => {
    const row = axes.value.find((a) => a.axis === axis);
    const axisName = row?.name.trim() || t(`compass.edit.axis${axis.toUpperCase()}`);
    return (["low", "high"] as const).map((side) => {
      const own = (side === "low" ? row?.low_name : row?.high_name)?.trim();
      // Before a side is named, the select says where it lands, which
      // is the same thing the axes block calls it.
      const fallback = t(`compass.edit.side${side === "low" ? "Low" : "High"}${axis.toUpperCase()}`);
      return { value: `${axis}_${side}` as Pole, label: `${axisName}: ${own || fallback}` };
    });
  }),
);

/* Quiz only: whether the result screen names the right answers. An
 * organiser running the same quiz twice in one evening turns it off. */
const revealAnswers = ref(true);

/* Whether somebody may reopen their own link and change what they
 * said. A quiz never offers it, so the switch is not drawn there. */
const answersEditable = ref(true);
const nameRequired = ref(false);
/* The switches live behind one fold, the same one every other edit page
 * ends with, and it starts closed every time. */
const advancedOpen = ref(false);

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
/* Kompas only: the two axes and their four sides. Empty until the
 * organiser names them, which the save refuses by name the moment
 * there is a question to point at one (``docs/design-kompas.md`` 4.4). */
const axes = ref<CompassAxisIn[]>([]);
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
      pole: (q.pole as Pole | null) ?? null,
      option_poles: (q.option_poles as Pole[] | null) ?? null,
    }));
    revealAnswers.value = existing.reveal_answers ?? true;
    answersEditable.value = existing.answers_editable ?? true;
    nameRequired.value = existing.name_required ?? false;
    axes.value = (existing.axes ?? []).map((a) => ({ ...a, axis: a.axis as "x" | "y" }));
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
//
// The resource is in the key because this page is three pages: without
// it, ``/form/new``, ``/quiz/new`` and ``/compass/new`` all wrote
// to ``form-edit-draft:new``, so a half-typed questionnaire came back
// on the kompas page — with a number question in it, which a kompas
// cannot ask, so the kind select rendered blank and the body rendered a
// number box.
const draftKey = computed(() => `${api.resource}-edit-draft:${props.formId ?? "new"}`);

interface FormEditDraft {
  nameNl: string;
  nameEn: string;
  descNl: string;
  descEn: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  formLocale: "nl" | "en";
  questions: QuestionDraft[];
  axes: CompassAxisIn[];
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
    axes: axes.value,
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
  axes.value = (d.axes ?? []).map((a) => ({ ...a }));
}

const { loadDraft, clearDraft } = useFormDraft<FormEditDraft>({
  key: draftKey,
  snapshot,
  apply: applyDraft,
  sources: [nameNl, nameEn, descNl, descEn, imageArtistInstagram, chapterId, formLocale, questions, axes],
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

/** An axis with no name, or a side with none, in words. Only a kompas
 *  has any, and only once there is something to name them for: a draft
 *  with neither questions nor axes saves, which is what an organiser
 *  coming back to it expects (``docs/design-kompas.md`` 4.4). */
function firstAxisNamingProblem(): string | null {
  if (!isCompass.value) return null;
  if (!questions.value.length && !axes.value.length) return null;
  for (const axis of ["x", "y"] as const) {
    const row = axes.value.find((a) => a.axis === axis);
    const name = row?.name.trim() ?? "";
    if (!name) return t("compass.edit.fillAxisName", { axis: axis.toUpperCase() });
    if (!row?.low_name.trim() || !row?.high_name.trim()) {
      return t("compass.edit.fillPoleNames", { name });
    }
  }
  return null;
}

/** An axis no question ever points at. Any of the four sides may go
 *  unused, which is the organiser's choice and sometimes the honest
 *  one; an axis nothing touches is a half-written kompas.
 *
 *  Checked after the per-question problems, and never before them:
 *  a question whose direction is still empty makes its axis look unused
 *  too, and being told "nobody can move on Economie" when the real
 *  answer is "question 1 has no side yet" sends an organiser to the
 *  wrong end of the page. Same order the server runs them in
 *  (``services/compass.validate_questions``). */
function axisCoverageProblem(): string | null {
  if (!isCompass.value || !questions.value.length) return null;
  const used = new Set(
    questions.value
      .flatMap((q) => (q.kind === "rating" ? [q.pole] : (q.option_poles ?? [])))
      .filter(Boolean)
      .map((pole) => (pole as string).split("_")[0]),
  );
  for (const axis of ["x", "y"] as const) {
    if (used.has(axis)) continue;
    const name = axes.value.find((a) => a.axis === axis)?.name.trim() ?? axis.toUpperCase();
    return t("compass.edit.axisUnused", { name });
  }
  return null;
}

/** The first thing wrong with the question list, in words, or null.
 *  Mirrors the rules in ``services/forms._validate_questions``,
 *  ``services/quizzes.validate_keys`` and
 *  ``services/compass.validate_questions``: the server is still the
 *  authority, this is so the answer arrives in Dutch and names the
 *  question. */
function firstQuestionProblem(): string | null {
  // Nothing to answer is a public page whose only button does nothing,
  // so it is refused here and again on the server.
  if (questions.value.length === 0) return L("edit.needsAQuestion");
  for (const [index, q] of questions.value.entries()) {
    const n = index + 1;
    if (!q.prompt.trim()) return L("edit.questionNeedsPrompt", { n });
    const choice = q.kind === "single_choice" || q.kind === "multi_choice";
    if (choice && q.options.length < 2) return L("edit.questionNeedsOptions", { n });
    if (isCompass.value) {
      if (q.kind === "rating" && !q.pole) return t("compass.edit.questionNeedsPole", { n });
      if (q.kind === "single_choice") {
        const poles = q.option_poles ?? [];
        if (poles.length !== q.options.length || poles.some((pole) => !pole)) {
          return t("compass.edit.questionNeedsOptionPoles", { n });
        }
      }
      continue;
    }
    if (!isQuiz.value || q.points <= 0) continue;
    if (choice && (q.correct_choices ?? []).length === 0) return t("quiz.edit.questionNeedsKey", { n });
    if (q.kind === "single_choice" && (q.correct_choices ?? []).length !== 1) {
      return t("quiz.edit.questionNeedsOneKey", { n });
    }
    if ((q.kind === "number" || q.kind === "rating") && q.correct_int === null) {
      return t("quiz.edit.questionNeedsKey", { n });
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
    pole: null,
    option_poles: null,
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
  // In the server's own order: an unnamed axis first, because nothing
  // can be rendered without the words; then each question, which names
  // itself; then the axis nothing points at, which is only a real
  // problem once every question is complete.
  const problem = firstAxisNamingProblem() ?? firstQuestionProblem() ?? axisCoverageProblem();
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
      answers_editable: answersEditable.value,
      name_required: nameRequired.value,
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
          pole: q.pole,
          option_poles: q.option_poles,
        }),
      ),
      axes: isCompass.value ? axes.value : [],
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
    :submit-label="isEdit ? L('edit.save') : L('edit.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
    <section class="form-section">
      <StartAccountField v-if="startActive" v-model="startEmail" />
      <AppInput
        v-model="title"
        :placeholder="titleFallback || L('edit.namePlaceholder')"
        fluid
      />
      <RichTextField
        v-model="body"
        :placeholder="t('form.edit.descriptionPlaceholder')"
        :fallback-html="bodyFallback || null"
      />
      <SelectField
        v-if="hasChapters"
        v-model="chapterId"
        :options="userChapterOptions"
        option-label="name"
        option-value="id"
        :placeholder="t('form.edit.chapterPlaceholder')"
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

    <!-- Kompas only, and above the questions because every question
         points at one of these: the words chosen here are the words
         every pole select below then offers. -->
    <section v-if="isCompass" class="form-section">
      <h2 class="section-heading">{{ t("compass.edit.axesHeading") }}</h2>
      <!-- No explainer: the placeholders carry what to type and the
           example to type it like, and the arrows say where each side
           lands. A paragraph above them would repeat the boxes
           underneath it. -->
      <CompassAxesEditor v-model="axes" />
    </section>

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
          :pointed="isCompass"
          :pole-options="poleOptions"
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

      <AppButton
        type="button"
        :label="L('edit.addQuestion')"
        icon="plus"
        severity="secondary"
        @click="addQuestion"
      />
    </section>


    <!-- Every switch, folded away: above it is the thing itself, under
         it the page language. One fold on all six products. -->
    <details class="advanced" :open="advancedOpen" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
      <summary>{{ advancedOpen ? t("common.advancedHide") : t("common.advancedShow") }}</summary>

      <!-- Off by default: a name real or not is what the contract
           offers, so an empty box is an answer. On when the answers are
           only useful attached to somebody. -->
      <section class="form-section">
        <label class="toggle-row" for="nameRequiredToggle">
          <AppToggle v-model="nameRequired" inputId="nameRequiredToggle" />
          <h2 class="section-heading">{{ t("common.nameRequired") }}</h2>
        </label>
        <p class="muted section-explainer">{{ t("common.nameRequiredExplainer") }}</p>
      </section>

      <!-- What happens after the questions are answered. A quiz has no
           edit at all, so it gets the reveal switch instead. -->
      <section v-if="!isQuiz" class="form-section">
        <label class="toggle-row" for="editableToggle">
          <AppToggle v-model="answersEditable" inputId="editableToggle" />
          <h2 class="section-heading">{{ t("form.edit.editableHeading") }}</h2>
        </label>
        <p class="muted section-explainer">{{ t("form.edit.editableExplainer") }}</p>
      </section>

      <section v-if="isQuiz" class="form-section">
        <label class="toggle-row" for="revealToggle">
          <AppToggle v-model="revealAnswers" inputId="revealToggle" />
          <h2 class="section-heading">{{ t("quiz.edit.revealHeading") }}</h2>
        </label>
        <p class="muted section-explainer">{{ t("quiz.edit.revealExplainer") }}</p>
      </section>
    </details>

    <section class="form-section">
      <h2 class="section-heading">{{ L("edit.localeHeading") }}</h2>
      <p class="muted section-explainer">{{ L("edit.localeExplainer") }}</p>
      <SelectField
        v-model="formLocale"
        :options="[
          { value: 'nl', label: t('form.edit.localeNl') },
          { value: 'en', label: t('form.edit.localeEn') },
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
