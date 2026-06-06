<script setup lang="ts">
import Button from "primevue/button";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import PublicHeader from "@/components/PublicHeader.vue";
import QuestionInput, { type Answer } from "@/components/QuestionInput.vue";
import { ApiError } from "@/api/client";
import { usePublicForm, useSubmitForm } from "@/composables/useForms";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ slug: string }>();

const { t, locale } = useI18n();
const toasts = useToasts();

// Per-question answer state, keyed by question id. Repopulated
// whenever the form payload arrives. Existing keys for questions
// that disappeared from a refetch drop on assignment, so an
// organiser editing the question set live can't strand stale
// answers in local state.
const answers = ref<Record<string, Answer>>({});
const submitted = ref(false);

const formQuery = usePublicForm(computed(() => props.slug));
const form = computed(() => formQuery.data.value ?? null);

const submitMutation = useSubmitForm();
const submitting = computed(() => submitMutation.isPending.value);

const error = computed<string | null>(() => {
  const err = formQuery.error.value;
  if (!err) return null;
  return err instanceof ApiError && err.status === 410
    ? t("forms.public.unavailable")
    : t("forms.public.loadFailed");
});

watch(
  form,
  (f) => {
    if (!f) return;
    locale.value = f.locale;
    const next: Record<string, Answer> = {};
    for (const q of f.questions) {
      if (q.kind === "rating") next[q.id] = { answer_int: null };
      else if (q.kind === "text" || q.kind === "short_text") next[q.id] = { answer_text: "" };
      else next[q.id] = { answer_choices: [] };
    }
    answers.value = next;
  },
  { immediate: true },
);

function isAnswered(question: { kind: string; id: string }): boolean {
  const a = answers.value[question.id] ?? {};
  if (question.kind === "rating") return a.answer_int != null;
  if (question.kind === "text" || question.kind === "short_text")
    return (a.answer_text ?? "").trim().length > 0;
  return (a.answer_choices ?? []).length > 0;
}

async function submit() {
  if (!form.value) return;
  // Client-side required-question check mirrors the backend.
  for (const q of form.value.questions) {
    if (q.required && !isAnswered(q)) {
      toasts.warn(q.prompt);
      return;
    }
  }

  // Build the wire payload. Drop the kind-incompatible fields per
  // answer so the request body stays tight — a noisy body breaks
  // the "what does Sentry show us" debugging story.
  const payload = form.value.questions.map((q) => {
    const a = answers.value[q.id] ?? {};
    if (q.kind === "rating") return { question_id: q.id, answer_int: a.answer_int ?? null };
    if (q.kind === "text" || q.kind === "short_text")
      return { question_id: q.id, answer_text: a.answer_text ?? "" };
    return { question_id: q.id, answer_choices: a.answer_choices ?? [] };
  });

  try {
    await submitMutation.mutateAsync({ slug: props.slug, payload: { answers: payload } });
    submitted.value = true;
  } catch (e) {
    const msg =
      e instanceof ApiError && e.status === 410
        ? t("forms.public.unavailable")
        : t("forms.public.submitFail");
    toasts.error(msg);
  }
}
</script>

<template>
  <div class="container stack">
    <PublicHeader />

    <!-- ``submitted`` beats ``error``: once a submit lands, no
         later refetch can flip the visitor back to a "no longer
         available" message. -->
    <AppCard v-if="submitted">
      <h2>{{ t("forms.public.thanks") }}</h2>
      <p class="muted">{{ t("forms.public.thanksBody") }}</p>
    </AppCard>

    <AppCard v-else-if="error" :stack="false">
      <p>{{ error }}</p>
    </AppCard>

    <AppCard v-else-if="!form" :stack="false">
      <p class="muted">{{ t("common.loading") }}</p>
    </AppCard>

    <template v-else>
      <AppCard>
        <h1>{{ form.name }}</h1>
      </AppCard>

      <form class="stack" novalidate @submit.prevent="submit">
        <AppCard v-for="q in form.questions" :key="q.id">
          <QuestionInput
            :question="q"
            :model-value="answers[q.id] ?? {}"
            @update:model-value="(v) => (answers[q.id] = v)"
          />
        </AppCard>
        <div class="submit-row">
          <Button
            type="submit"
            :label="t('forms.public.submit')"
            :loading="submitting"
          />
        </div>
      </form>
    </template>
  </div>
</template>

<style scoped>
.submit-row {
  display: flex;
  justify-content: flex-end;
}
</style>
