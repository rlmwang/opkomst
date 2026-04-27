<script setup lang="ts">
import Button from "primevue/button";
import Textarea from "primevue/textarea";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import PublicHeader from "@/components/PublicHeader.vue";
import RatingScale from "@/components/RatingScale.vue";
import { ApiError } from "@/api/client";
import { useToasts } from "@/lib/toasts";
import {
  type FeedbackForm,
  type FeedbackQuestion,
  useFeedbackStore,
} from "@/stores/feedback";

// `slug` is declared so the router populates it via `props: true`; the
// page reads the token from the query string and otherwise doesn't
// reference the slug, so we don't bind it.
defineProps<{ slug: string }>();

const { t, locale } = useI18n();
const route = useRoute();
const toasts = useToasts();
const store = useFeedbackStore();

const form = ref<FeedbackForm | null>(null);
const ratings = ref<Record<string, number | null>>({});
const texts = ref<Record<string, string>>({});
const error = ref<string | null>(null);
const submitting = ref(false);
const submitted = ref(false);

const token = (route.query.t as string | undefined) ?? "";

onMounted(async () => {
  if (!token) {
    error.value = t("feedback.expired");
    return;
  }
  try {
    form.value = await store.getForm(token);
    // Render the questionnaire in the event's configured language —
    // matches the email the visitor was sent in. localStorage is
    // not touched.
    locale.value = form.value.event_locale;
    for (const q of form.value.questions) {
      if (q.kind === "rating") ratings.value[q.id] = null;
      if (q.kind === "text") texts.value[q.id] = "";
    }
  } catch (e) {
    error.value =
      e instanceof ApiError && (e.status === 410 || e.status === 404)
        ? t("feedback.expired")
        : t("feedback.loadFailed");
  }
});

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
  if (!form.value) return;
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

  submitting.value = true;
  try {
    await store.submit(token, answers);
    submitted.value = true;
  } catch (e) {
    const msg =
      e instanceof ApiError && (e.status === 410 || e.status === 404)
        ? t("feedback.expired")
        : t("feedback.submitFail");
    toasts.error(msg);
  } finally {
    submitting.value = false;
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
      <AppCard>
        <h1>{{ t("feedback.title", { name: form.event_name }) }}</h1>
        <p class="muted intro">{{ t("feedback.intro") }}</p>
      </AppCard>

      <form class="stack" novalidate @submit.prevent="submit">
        <AppCard v-for="q in form.questions" :key="q.id">
          <label class="prompt">
            {{ questionPrompt(q) }}
            <span v-if="q.required" class="required">*</span>
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
        <Button type="submit" :label="t('feedback.submit')" :loading="submitting" />
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
.required {
  color: var(--brand-red);
  margin-left: 0.125rem;
}
</style>
