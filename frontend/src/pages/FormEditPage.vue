<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import FormPageShell from "@/components/FormPageShell.vue";
import QuestionEditor, { type QuestionDraft } from "@/components/QuestionEditor.vue";
import { chapterList, useChapters } from "@/composables/useChapters";
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
const formLocale = ref<"nl" | "en">((locale.value as "nl" | "en") ?? "nl");
const questions = ref<QuestionDraft[]>([]);
const submitting = ref(false);

// Edit-mode hydration. ``useForm`` caches per-form-id so we only
// pay one round-trip even when navigating back through the list.
const existingQuery = computed(() => (props.formId ? props.formId : ""));
const formQuery = isEdit.value ? useForm(existingQuery) : null;

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
});

// Edit-mode: copy the existing form into the local refs once the
// fetch lands. ``immediate`` so the snapshot also runs if the
// cache already had the row (e.g. arriving from the details page).
watch(
  () => formQuery?.data.value,
  (existing) => {
    if (!existing) return;
    name.value = existing.name;
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
  },
  { immediate: true },
);

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
    void router.push(`/forms/${result.id}/details`);
  } catch {
    toasts.error(t("forms.edit.saveFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <FormPageShell
    :title="isEdit ? t('forms.edit.editTitle') : t('forms.edit.newTitle')"
    :submit-label="isEdit ? t('forms.edit.save') : t('forms.edit.create')"
    :submitting="submitting"
    @submit="submit"
    @cancel="cancel"
  >
    <section class="form-section">
      <InputText v-model="name" :placeholder="t('forms.edit.namePlaceholder')" fluid />
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
</style>
