<script setup lang="ts">
import Button from "primevue/button";
import Textarea from "primevue/textarea";
import { useToast } from "primevue/usetoast";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import BrandMark from "@/components/BrandMark.vue";
import RatingScale from "@/components/RatingScale.vue";
import { ApiError } from "@/api/client";
import {
  type FeedbackForm,
  type FeedbackQuestion,
  useFeedbackStore,
} from "@/stores/feedback";

// `slug` is declared so the router populates it via `props: true`; the
// page reads the token from the query string and otherwise doesn't
// reference the slug, so we don't bind it.
defineProps<{ slug: string }>();

const { t } = useI18n();
const route = useRoute();
const toast = useToast();
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
      toast.add({ severity: "warn", summary: questionPrompt(q), life: 2500 });
      return;
    }
    if (q.kind === "text" && !texts.value[q.id].trim()) {
      toast.add({ severity: "warn", summary: questionPrompt(q), life: 2500 });
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
    toast.add({ severity: "error", summary: msg, life: 3000 });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="container stack">
    <header class="public-header">
      <BrandMark />
    </header>

    <div v-if="error" class="card">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="submitted" class="card stack">
      <h2>{{ t("feedback.thanks") }}</h2>
      <p class="muted">{{ t("feedback.thanksBody") }}</p>
    </div>

    <template v-else-if="form">
      <div class="card stack">
        <h1>{{ t("feedback.title", { name: form.event_name }) }}</h1>
        <p class="muted intro">{{ t("feedback.intro") }}</p>
      </div>

      <form class="stack" @submit.prevent="submit">
        <div v-for="q in form.questions" :key="q.id" class="card stack">
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
        </div>
        <Button type="submit" :label="t('feedback.submit')" :loading="submitting" />
      </form>
    </template>
  </div>
</template>

<style scoped>
.public-header {
  padding: 1rem 0;
}
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
