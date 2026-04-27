<script setup lang="ts">
import Textarea from "primevue/textarea";
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import RatingScale from "@/components/RatingScale.vue";
import { type FeedbackQuestion, useFeedbackStore } from "@/stores/feedback";

const { t } = useI18n();
const store = useFeedbackStore();

onMounted(async () => {
  if (store.questions.length === 0) await store.fetchQuestions();
});

function prompt(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.prompt`);
}

function low(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.labelLow`);
}

function high(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.labelHigh`);
}

function placeholder(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.placeholder`);
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <AppCard>
      <h1>{{ t("feedback.preview.title") }}</h1>
      <p class="muted">{{ t("feedback.preview.intro") }}</p>
    </AppCard>

    <AppCard v-for="q in store.questions" :key="q.id" class="preview-card">
      <label class="prompt">
        {{ q.ordinal }}. {{ prompt(q) }}
        <span v-if="q.required" class="required">*</span>
      </label>
      <RatingScale
        v-if="q.kind === 'rating'"
        :model-value="null"
        :label-low="low(q)"
        :label-high="high(q)"
        @update:model-value="() => {}"
      />
      <Textarea
        v-else
        :model-value="''"
        :placeholder="placeholder(q)"
        rows="3"
        readonly
        fluid
      />
    </AppCard>
  </div>
</template>

<style scoped>
.preview-card {
  pointer-events: auto;
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
