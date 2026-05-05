<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { useToasts } from "@/lib/toasts";
import { useMemberSurveyResults } from "@/composables/useMemberSurvey";

const { t, d } = useI18n();
const toasts = useToasts();
const { data, isLoading, error } = useMemberSurveyResults();

const results = computed(() => data.value ?? null);

// Absolute URL of the public form, computed at runtime so it
// follows wherever the app is hosted (localhost in dev, the prod
// hostname in prod). The path is the one declared in the router.
const formUrl = computed(() =>
  typeof window === "undefined"
    ? "/s/nieuwe-leden"
    : `${window.location.origin}/s/nieuwe-leden`,
);

// Sorted barriers — most-cited first. Stable order in the keys
// from the server is by the canonical enum sequence; for the
// admin view the bar-chart reads better when sorted by count.
const sortedBarriers = computed(() => {
  if (!results.value) return [];
  return Object.entries(results.value.barrier_counts).sort(
    (a, b) => b[1] - a[1],
  );
});

function pct(distribution: number[], idx: number): number {
  const total = distribution.reduce((a, b) => a + b, 0);
  return total === 0 ? 0 : Math.round((distribution[idx] / total) * 100);
}

function fmtDate(iso: string): string {
  return d(new Date(iso), "short");
}

async function copyFormLink() {
  try {
    await navigator.clipboard.writeText(formUrl.value);
    toasts.success(t("event.share.linkCopied"));
  } catch {
    /* clipboard unavailable — user can copy the visible URL by hand */
  }
}

function csvEscape(v: unknown): string {
  const s = String(v ?? "");
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function downloadCsv() {
  if (!results.value || results.value.response_count === 0) return;
  try {
    const header = [
      t("memberSurvey.results.submittedAt"),
      t("memberSurvey.namePlaceholder"),
      t("memberSurvey.q1.prompt"),
      t("memberSurvey.q2.prompt"),
      t("memberSurvey.q3.prompt"),
      t("memberSurvey.q4.prompt"),
      t("memberSurvey.q4.otherLabel"),
      t("memberSurvey.q5.prompt"),
      t("memberSurvey.q6.prompt"),
    ];
    const rows = results.value.responses.map((r) => [
      r.created_at,
      r.first_name ?? "",
      r.q1_connected,
      r.q2_clarity,
      r.q3_likelihood,
      r.q4_barriers.map((k) => t(`memberSurvey.barriers.${k}`)).join("; "),
      r.q4_other_text ?? "",
      r.q5_helps ?? "",
      r.q6_anything_else ?? "",
    ]);
    const csv = [header, ...rows].map((r) => r.map(csvEscape).join(",")).join("\n");
    const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const today = new Date().toISOString().slice(0, 10);
    a.download = `${today}-nieuwe-leden-feedback.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toasts.error(t("feedback.summary.csvFail"));
  }
}
</script>

<template>
  <div>
    <AppHeader />

    <div class="container stack">
      <AppCard>
        <div class="title-row">
          <h1>{{ t("memberSurvey.results.title") }}</h1>
          <Button
            :label="t('feedback.summary.exportCsv')"
            size="small"
            severity="secondary"
            text
            icon="pi pi-download"
            :disabled="!results || results.response_count === 0"
            @click="downloadCsv"
          />
        </div>
        <p class="muted">{{ t("memberSurvey.results.subtitle") }}</p>
        <div class="link-row">
          <a :href="formUrl" target="_blank" rel="noopener">{{ formUrl }}</a>
          <Button
            icon="pi pi-copy"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('event.share.copyLink')"
            :aria-label="t('event.share.copyLink')"
            @click="copyFormLink"
          />
        </div>
        <p class="muted hint">{{ t("memberSurvey.results.formLinkHint") }}</p>
      </AppCard>

      <AppCard v-if="isLoading">
        <p class="muted">{{ t("common.loading") }}</p>
      </AppCard>

      <AppCard v-else-if="error">
        <p>{{ t("common.error") }}</p>
      </AppCard>

      <template v-else-if="results">
        <AppCard>
          <p class="response-count">
            {{ t("memberSurvey.results.responseCount", { n: results.response_count }) }}
          </p>
        </AppCard>

        <AppCard v-if="results.response_count === 0">
          <p class="muted">{{ t("memberSurvey.results.noResponses") }}</p>
        </AppCard>

        <template v-else>
          <AppCard>
            <div class="rating-block">
              <div class="rating-row">
                <div class="rating-label">{{ t("memberSurvey.q1.prompt") }}</div>
                <div class="rating-value">{{ results.q1_connected.average?.toFixed(1) ?? "—" }} / 5</div>
              </div>
              <div class="bars">
                <div v-for="i in 5" :key="i" class="bar-row">
                  <span class="bar-num">{{ i }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: pct(results.q1_connected.distribution, i - 1) + '%' }" />
                  </div>
                  <span class="bar-count">{{ results.q1_connected.distribution[i - 1] }}</span>
                </div>
              </div>
            </div>

            <div class="rating-block">
              <div class="rating-row">
                <div class="rating-label">{{ t("memberSurvey.q2.prompt") }}</div>
                <div class="rating-value">{{ results.q2_clarity.average?.toFixed(1) ?? "—" }} / 5</div>
              </div>
              <div class="bars">
                <div v-for="i in 5" :key="i" class="bar-row">
                  <span class="bar-num">{{ i }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: pct(results.q2_clarity.distribution, i - 1) + '%' }" />
                  </div>
                  <span class="bar-count">{{ results.q2_clarity.distribution[i - 1] }}</span>
                </div>
              </div>
            </div>

            <div class="rating-block">
              <div class="rating-row">
                <div class="rating-label">{{ t("memberSurvey.q3.prompt") }}</div>
                <div class="rating-value">{{ results.q3_likelihood.average?.toFixed(1) ?? "—" }} / 5</div>
              </div>
              <div class="bars">
                <div v-for="i in 5" :key="i" class="bar-row">
                  <span class="bar-num">{{ i }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: pct(results.q3_likelihood.distribution, i - 1) + '%' }" />
                  </div>
                  <span class="bar-count">{{ results.q3_likelihood.distribution[i - 1] }}</span>
                </div>
              </div>
            </div>
          </AppCard>

          <AppCard>
            <h2>{{ t("memberSurvey.results.barriersTitle") }}</h2>
            <div class="barrier-list">
              <div v-for="[key, count] in sortedBarriers" :key="key" class="barrier-row">
                <div class="barrier-label">{{ t(`memberSurvey.barriers.${key}`) }}</div>
                <div class="barrier-track">
                  <div
                    class="barrier-fill"
                    :style="{ width: (results.response_count ? Math.round((count / results.response_count) * 100) : 0) + '%' }"
                  />
                </div>
                <div class="barrier-count">{{ count }}</div>
              </div>
            </div>
          </AppCard>

          <AppCard>
            <h2>{{ t("memberSurvey.results.responsesTitle") }}</h2>
            <div class="response-list">
              <div v-for="r in results.responses" :key="r.id" class="response">
                <div class="response-head">
                  <strong>{{ r.first_name || t("memberSurvey.results.anonymous") }}</strong>
                  <span class="muted small">{{ fmtDate(r.created_at) }}</span>
                </div>
                <div class="response-ratings muted small">
                  Q1 {{ r.q1_connected }} · Q2 {{ r.q2_clarity }} · Q3 {{ r.q3_likelihood }}
                </div>
                <div v-if="r.q4_barriers.length" class="response-barriers">
                  <span v-for="b in r.q4_barriers" :key="b" class="chip">
                    {{ t(`memberSurvey.barriers.${b}`) }}
                  </span>
                </div>
                <div v-else class="muted small">{{ t("memberSurvey.results.noBarriers") }}</div>
                <div v-if="r.q4_other_text" class="response-text">
                  <em>{{ t("memberSurvey.q4.otherLabel") }}:</em> {{ r.q4_other_text }}
                </div>
                <div v-if="r.q5_helps" class="response-text">
                  <em>{{ t("memberSurvey.q5.prompt") }}</em><br />{{ r.q5_helps }}
                </div>
                <div v-if="r.q6_anything_else" class="response-text">
                  <em>{{ t("memberSurvey.q6.prompt") }}</em><br />{{ r.q6_anything_else }}
                </div>
              </div>
            </div>
          </AppCard>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.container {
  max-width: 880px;
  margin: 0 auto;
  padding: 1rem;
}
.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.link-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  margin-top: 0.75rem;
}
.link-row a {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hint {
  font-size: 0.8125rem;
  margin-top: 0.375rem;
}
.response-count {
  font-size: 1.125rem;
  font-weight: 600;
}
.rating-block + .rating-block {
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--brand-border);
}
.rating-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.5rem;
}
.rating-label {
  font-weight: 600;
}
.rating-value {
  font-variant-numeric: tabular-nums;
  color: var(--brand-red);
  font-weight: 600;
}
.bars {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.bar-row {
  display: grid;
  grid-template-columns: 1.25rem 1fr 2rem;
  align-items: center;
  gap: 0.5rem;
}
.bar-num {
  font-size: 0.8125rem;
  color: var(--brand-text-muted, #5e5a52);
}
.bar-track {
  height: 0.625rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 0.25rem;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: var(--brand-red, #9f000b);
}
.bar-count {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 0.8125rem;
  color: var(--brand-text-muted, #5e5a52);
}
.barrier-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.barrier-row {
  display: grid;
  grid-template-columns: minmax(12rem, 1.5fr) 2fr 2.5rem;
  align-items: center;
  gap: 0.625rem;
}
.barrier-label {
  font-size: 0.9375rem;
}
.barrier-track {
  height: 0.5rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 0.25rem;
  overflow: hidden;
}
.barrier-fill {
  height: 100%;
  background: var(--brand-red, #9f000b);
}
.barrier-count {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.response-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.response {
  padding: 0.75rem 0;
  border-top: 1px solid var(--brand-border);
}
.response:first-child {
  border-top: none;
  padding-top: 0;
}
.response-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.25rem;
}
.response-ratings {
  margin-bottom: 0.375rem;
}
.response-barriers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0.375rem 0;
}
.chip {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-surface);
  font-size: 0.8125rem;
}
.response-text {
  margin-top: 0.375rem;
  font-size: 0.9375rem;
  line-height: 1.45;
}
.small {
  font-size: 0.8125rem;
}
.muted {
  color: var(--brand-text-muted, #5e5a52);
}
.stack > * + * {
  margin-top: 1rem;
}
</style>
