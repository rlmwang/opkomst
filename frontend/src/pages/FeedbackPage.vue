<script setup lang="ts">
import Button from "primevue/button";
import Textarea from "primevue/textarea";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import PublicHeader from "@/components/PublicHeader.vue";
import RatingScale from "@/components/RatingScale.vue";
import { ApiError } from "@/api/client";
import {
  type FeedbackQuestion,
  useFeedbackForm,
  useFeedbackPreview,
  useSubmitFeedback,
} from "@/composables/useFeedback";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ slug: string }>();

const { t, locale } = useI18n();
const route = useRoute();
const toasts = useToasts();

const ratings = ref<Record<string, number | null>>({});
const texts = ref<Record<string, string>>({});
const submitted = ref(false);

const token = (route.query.t as string | undefined) ?? "";
const isPreview = token === "preview";

const formQuery = useFeedbackForm(token, !isPreview && Boolean(token));
const previewQuery = useFeedbackPreview(
  computed(() => props.slug),
  isPreview,
);
const submitMutation = useSubmitFeedback();

const form = computed(() =>
  isPreview ? previewQuery.data.value ?? null : formQuery.data.value ?? null,
);
const submitting = computed(() => submitMutation.isPending.value);

const error = computed<string | null>(() => {
  if (!token) return t("feedback.expired");
  const err = isPreview ? previewQuery.error.value : formQuery.error.value;
  if (!err) return null;
  return err instanceof ApiError && (err.status === 410 || err.status === 404)
    ? t("feedback.expired")
    : t("feedback.loadFailed");
});

watch(
  form,
  (f) => {
    if (!f) return;
    locale.value = f.event_locale;
    for (const q of f.questions) {
      if (q.kind === "rating") ratings.value[q.id] = null;
      if (q.kind === "text") texts.value[q.id] = "";
    }
  },
  { immediate: true },
);

function questionPrompt(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.prompt`);
}

function ratingLabel(q: FeedbackQuestion, end: "Low" | "High"): string {
  return t(`feedback.questions.${q.key}.label${end}`);
}

function textPlaceholder(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.placeholder`);
}

async function submit() {
  if (!form.value || isPreview) return;
  // Client-side check on required questions, mirrors backend.
  for (const q of form.value.questions) {
    if (!q.required) continue;
    if (q.kind === "rating" && ratings.value[q.id] == null) {
      toasts.warn(questionPrompt(q));
      return;
    }
    if (q.kind === "text" && !texts.value[q.id].trim()) {
      toasts.warn(questionPrompt(q));
      return;
    }
  }

  const answers = form.value.questions.map((q) =>
    q.kind === "rating"
      ? { question_id: q.id, answer_int: ratings.value[q.id] }
      : { question_id: q.id, answer_text: texts.value[q.id] || null },
  );

  try {
    await submitMutation.mutateAsync({ token, answers });
    submitted.value = true;
  } catch (e) {
    const msg =
      e instanceof ApiError && (e.status === 410 || e.status === 404)
        ? t("feedback.expired")
        : t("feedback.submitFail");
    toasts.error(msg);
  }
}
</script>

<template>
  <div class="container stack">
    <PublicHeader />

    <AppCard v-if="error" :stack="false">
      <p>{{ error }}</p>
    </AppCard>

    <AppCard v-else-if="submitted">
      <h2>{{ t("feedback.thanks") }}</h2>
      <p class="muted">{{ t("feedback.thanksBody") }}</p>
    </AppCard>

    <template v-else-if="form">
      <AppCard v-if="isPreview" :stack="false" class="preview-banner">
        <p>{{ t("feedback.previewBanner") }}</p>
      </AppCard>

      <AppCard>
        <h1>{{ t("feedback.title", { name: form.event_name }) }}</h1>
        <p class="muted intro">{{ t("feedback.intro") }}</p>
      </AppCard>

      <form class="stack" novalidate @submit.prevent="submit">
        <AppCard v-for="q in form.questions" :key="q.id">
          <label class="prompt">
            {{ questionPrompt(q) }}
          </label>
          <RatingScale
            v-if="q.kind === 'rating'"
            :model-value="ratings[q.id]"
            :label-low="ratingLabel(q, 'Low')"
            :label-high="ratingLabel(q, 'High')"
            @update:model-value="ratings[q.id] = $event"
          />
          <Textarea
            v-else
            v-model="texts[q.id]"
            :placeholder="textPlaceholder(q)"
            :maxlength="500"
            rows="3"
            auto-resize
            fluid
          />
        </AppCard>
        <Button
          type="submit"
          :label="t('feedback.submit')"
          :loading="submitting"
          :disabled="isPreview"
        />
      </form>
    </template>
  </div>
</template>

<style scoped>
.intro {
  font-size: 0.9375rem;
}
.prompt {
  font-weight: 600;
  font-size: 1.0625rem;
  line-height: 1.4;
}
.preview-banner {
  border: 1px dashed var(--brand-primary);
  background: color-mix(in srgb, var(--brand-primary) 6%, transparent);
}
.preview-banner p {
  margin: 0;
  font-size: 0.9375rem;
  color: var(--brand-primary);
}
</style>
