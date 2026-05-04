<script setup lang="ts">
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import InputText from "primevue/inputtext";
import Textarea from "primevue/textarea";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import PublicHeader from "@/components/PublicHeader.vue";
import RatingScale from "@/components/RatingScale.vue";
import { useToasts } from "@/lib/toasts";
import { useSubmitMemberSurvey } from "@/composables/useMemberSurvey";

const { t } = useI18n();
const toasts = useToasts();
const submit = useSubmitMemberSurvey();

// Stable barrier identifiers — kept on the client too so this page
// can render without an extra GET round-trip. The server validates
// the same set on submit, so a drift here surfaces as a 400, not
// a silent corruption.
const BARRIER_KEYS = [
  "no_time",
  "distance_or_cost",
  "lacks_knowledge",
  "no_clear_step",
  "knows_no_one",
  "nobody_asked",
  "not_for_me",
  "doubts_impact",
] as const;

const firstName = ref("");
const q1 = ref<number | null>(null);
const q2 = ref<number | null>(null);
const q3 = ref<number | null>(null);
const barriers = ref<string[]>([]);
const otherText = ref("");
const helps = ref("");
const submitted = ref(false);

const submitting = computed(() => submit.isPending.value);

async function onSubmit() {
  if (q1.value == null || q2.value == null || q3.value == null) {
    toasts.warn(t("memberSurvey.submitFail"));
    return;
  }
  try {
    await submit.mutateAsync({
      first_name: firstName.value.trim() || null,
      q1_connected: q1.value,
      q2_clarity: q2.value,
      q3_likelihood: q3.value,
      q4_barriers: barriers.value,
      q4_other_text: otherText.value.trim() || null,
      q5_helps: helps.value.trim() || null,
    });
    submitted.value = true;
  } catch {
    toasts.error(t("memberSurvey.submitFail"));
  }
}
</script>

<template>
  <div class="container stack">
    <PublicHeader />

    <AppCard v-if="submitted">
      <h2>{{ t("memberSurvey.thanks") }}</h2>
      <p class="muted">{{ t("memberSurvey.thanksBody") }}</p>
    </AppCard>

    <template v-else>
      <AppCard>
        <h1>{{ t("memberSurvey.title") }}</h1>
        <p class="muted intro">{{ t("memberSurvey.intro") }}</p>
      </AppCard>

      <form class="stack" novalidate @submit.prevent="onSubmit">
        <AppCard>
          <InputText
            id="first-name"
            v-model="firstName"
            :placeholder="t('memberSurvey.namePlaceholder')"
            maxlength="80"
            fluid
          />
          <p class="muted note">{{ t("memberSurvey.nameNote") }}</p>
        </AppCard>

        <AppCard>
          <label class="prompt">{{ t("memberSurvey.q1.prompt") }}</label>
          <RatingScale
            :model-value="q1"
            :label-low="t('memberSurvey.q1.labelLow')"
            :label-high="t('memberSurvey.q1.labelHigh')"
            @update:model-value="q1 = $event"
          />
        </AppCard>

        <AppCard>
          <label class="prompt">{{ t("memberSurvey.q2.prompt") }}</label>
          <RatingScale
            :model-value="q2"
            :label-low="t('memberSurvey.q2.labelLow')"
            :label-high="t('memberSurvey.q2.labelHigh')"
            @update:model-value="q2 = $event"
          />
        </AppCard>

        <AppCard>
          <label class="prompt">{{ t("memberSurvey.q3.prompt") }}</label>
          <RatingScale
            :model-value="q3"
            :label-low="t('memberSurvey.q3.labelLow')"
            :label-high="t('memberSurvey.q3.labelHigh')"
            @update:model-value="q3 = $event"
          />
        </AppCard>

        <AppCard>
          <label class="prompt">{{ t("memberSurvey.q4.prompt") }}</label>
          <p class="muted hint">{{ t("memberSurvey.q4.hint") }}</p>
          <div class="checkbox-list">
            <label v-for="key in BARRIER_KEYS" :key="key" class="checkbox-row">
              <Checkbox v-model="barriers" :input-id="`barrier-${key}`" :value="key" />
              <span>{{ t(`memberSurvey.barriers.${key}`) }}</span>
            </label>
          </div>
          <label class="other-label" for="q4-other">{{ t("memberSurvey.q4.otherLabel") }}</label>
          <Textarea
            id="q4-other"
            v-model="otherText"
            :placeholder="t('memberSurvey.q4.otherPlaceholder')"
            :maxlength="500"
            rows="2"
            auto-resize
            fluid
          />
        </AppCard>

        <AppCard>
          <label class="prompt" for="q5-helps">{{ t("memberSurvey.q5.prompt") }}</label>
          <Textarea
            id="q5-helps"
            v-model="helps"
            :placeholder="t('memberSurvey.q5.placeholder')"
            :maxlength="2000"
            rows="4"
            auto-resize
            fluid
          />
        </AppCard>

        <div class="submit-row">
          <Button
            type="submit"
            :label="submitting ? t('memberSurvey.submitting') : t('memberSurvey.submit')"
            :loading="submitting"
          />
        </div>
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
.note,
.hint {
  font-size: 0.875rem;
  margin-top: 0.375rem;
}
.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.9375rem;
  cursor: pointer;
}
.other-label {
  display: block;
  margin-top: 0.5rem;
  margin-bottom: 0.25rem;
  font-size: 0.875rem;
  color: var(--brand-text-muted, #5e5a52);
}
.submit-row {
  display: flex;
  justify-content: flex-end;
}
</style>
