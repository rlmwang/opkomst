<script setup lang="ts">
import Button from "primevue/button";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppHeader from "@/components/AppHeader.vue";
import { type EventOut, type EventStats, useEventsStore } from "@/stores/events";
import { type FeedbackSummary, useFeedbackStore } from "@/stores/feedback";

const props = defineProps<{ eventId: string }>();

const { t, locale } = useI18n();
const events = useEventsStore();
const feedback = useFeedbackStore();
const event = ref<EventOut | null>(null);
const stats = ref<EventStats | null>(null);
const summary = ref<FeedbackSummary | null>(null);

function localeTag(): string {
  return locale.value === "en" ? "en-GB" : "nl-NL";
}

onMounted(async () => {
  if (events.all.length === 0) await events.fetchAll();
  event.value = events.all.find((e: EventOut) => e.id === props.eventId) ?? null;
  const [s, fs] = await Promise.all([
    events.getStats(props.eventId),
    feedback.getSummary(props.eventId).catch(() => null),
  ]);
  stats.value = s;
  summary.value = fs;
});

function publicUrl(slug: string): string {
  return `${window.location.origin}/e/${slug}`;
}

function qrUrl(slug: string): string {
  return `/api/v1/events/by-slug/${slug}/qr.png`;
}

const responsesLine = computed(() => {
  if (!summary.value) return "";
  const rate = `${Math.round(summary.value.response_rate * 100)}%`;
  return t("feedback.summary.responsesOf", {
    responses: summary.value.submission_count,
    signups: summary.value.signup_count,
    rate,
  });
});

function questionPrompt(key: string): string {
  return t(`feedback.questions.${key}.prompt`);
}

function bar(distribution: number[], idx: number): { width: string; count: number } {
  const max = Math.max(...distribution, 1);
  return { width: `${Math.round((distribution[idx] / max) * 100)}%`, count: distribution[idx] };
}

// Display order for the email-status pills. Keep "sent" prominent
// (the success state organisers care about) and degrade through the
// failure modes; not_applicable trails as the no-action bucket.
const HEALTH_KEYS = ["sent", "pending", "bounced", "complaint", "failed", "not_applicable"] as const;
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <template v-if="event && stats">
      <div class="title-row">
        <div>
          <h1>{{ event.name }}</h1>
          <p class="muted">{{ event.location }} · {{ new Date(event.starts_at).toLocaleString(localeTag()) }}</p>
        </div>
        <router-link :to="`/events/${event.id}/edit`">
          <Button :label="t('common.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
        </router-link>
      </div>

      <div class="card stack">
        <h2>{{ t("event.signupsTitle") }}</h2>
        <p>{{ t("event.signupsTotals", { signups: stats.total_signups, attendees: stats.total_attendees }) }}</p>
        <ul v-if="Object.keys(stats.by_source).length > 0">
          <li v-for="(count, src) in stats.by_source" :key="src">
            {{ src }}: {{ count }}
          </li>
        </ul>
      </div>

      <div v-if="summary" class="card stack">
        <h2>{{ t("feedback.email.title") }}</h2>
        <div class="email-health">
          <div v-for="key in HEALTH_KEYS" :key="key" class="health-pill" :class="`health-${key}`">
            <span class="count">{{ summary.email_health[key] }}</span>
            <span class="label">{{ t(`feedback.email.${key}`) }}</span>
          </div>
        </div>
      </div>

      <div class="card stack">
        <div class="feedback-header">
          <h2>{{ t("feedback.summary.title") }}</h2>
          <router-link to="/questionnaire">
            <Button :label="t('feedback.preview.open')" size="small" severity="secondary" text icon="pi pi-eye" />
          </router-link>
        </div>
        <p v-if="!summary || summary.submission_count === 0" class="muted">
          {{ t("feedback.summary.noResponsesYet") }}
        </p>
        <template v-else>
          <p>{{ responsesLine }}</p>
          <div v-for="q in summary.questions" :key="q.question_id" class="q-block">
            <p class="q-prompt">{{ questionPrompt(q.key) }}</p>
            <template v-if="q.kind === 'rating' && q.rating_distribution">
              <p class="muted q-meta">
                {{ t("feedback.summary.responses", { n: q.response_count }) }}
                <template v-if="q.rating_average">
                  · {{ t("feedback.summary.average", { avg: q.rating_average.toFixed(1) }) }}
                </template>
              </p>
              <div class="bars">
                <div v-for="i in 5" :key="i" class="bar-row">
                  <span class="bar-label">{{ i }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: bar(q.rating_distribution, i - 1).width }" />
                  </div>
                  <span class="bar-count">{{ q.rating_distribution[i - 1] }}</span>
                </div>
              </div>
            </template>
            <template v-else-if="q.kind === 'text'">
              <p v-if="!q.texts || q.texts.length === 0" class="muted q-meta">
                {{ t("feedback.summary.noTextResponses") }}
              </p>
              <ul v-else class="texts">
                <li v-for="(txt, i) in q.texts" :key="i">{{ txt }}</li>
              </ul>
            </template>
          </div>
        </template>
      </div>

      <div class="card stack">
        <h2>{{ t("event.shareTitle") }}</h2>
        <p>
          <a :href="publicUrl(event.slug)" target="_blank" rel="noopener">{{ publicUrl(event.slug) }}</a>
        </p>
        <img :src="qrUrl(event.slug)" alt="QR" class="qr" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.title-row h1 { margin: 0 0 0.25rem; }
.qr {
  width: 200px;
  height: 200px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  padding: 0.5rem;
}
.feedback-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.feedback-header h2 { margin: 0; }
.q-block {
  border-top: 1px solid var(--brand-border);
  padding-top: 0.75rem;
  margin-top: 0.25rem;
}
.q-block:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}
.q-prompt {
  margin: 0 0 0.5rem;
  font-weight: 600;
}
.q-meta {
  margin: 0 0 0.5rem;
}
.bars {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.bar-row {
  display: grid;
  grid-template-columns: 1.25rem 1fr 2.5rem;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
.bar-label {
  color: var(--brand-text-muted);
}
.bar-track {
  height: 0.625rem;
  background: var(--brand-border);
  border-radius: 999px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: var(--brand-red);
  border-radius: 999px;
}
.bar-count {
  text-align: right;
  color: var(--brand-text-muted);
}
.texts {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.texts li {
  line-height: 1.45;
}

.email-health {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.health-pill {
  display: inline-flex;
  flex-direction: column;
  gap: 0.125rem;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 0.875rem;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
  background: var(--brand-bg);
  min-width: 4.5rem;
}
.health-pill .count {
  font-weight: 700;
  font-size: 1.0625rem;
  line-height: 1;
}
.health-pill .label {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
}
.health-sent { background: #e6f4e6; border-color: #b7d8b7; }
.health-sent .count { color: #2d6a2d; }
.health-pending { background: #fdf3d8; border-color: #ead9b3; }
.health-pending .count { color: #8a6915; }
.health-bounced, .health-failed, .health-complaint {
  background: #fbdadc;
  border-color: #f5b0b4;
}
.health-bounced .count, .health-failed .count, .health-complaint .count {
  color: #9f000b;
}
.health-not_applicable .count { color: var(--brand-text-muted); }
</style>
