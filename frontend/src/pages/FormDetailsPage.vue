<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import {
  fetchFormSubmissions,
  useForm,
  useFormSummary,
} from "@/composables/useForms";
import { filenameSlug } from "@/lib/filename-slug";
import { publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ formId: string }>();

const { t } = useI18n();
const toasts = useToasts();

const formQuery = useForm(computed(() => props.formId));
const form = computed(() => formQuery.data.value ?? null);

const summaryQuery = useFormSummary(computed(() => props.formId));
const summary = computed(() => summaryQuery.data.value ?? null);

async function copyLink() {
  if (!form.value) return;
  try {
    await navigator.clipboard.writeText(publicFormUrl(form.value.slug));
    toasts.success(t("forms.details.linkCopied"));
  } catch {
    /* clipboard unavailable */
  }
}

// --- CSV export ---------------------------------------------------
// One row per submission. Columns: submission id + submission
// time + one per question (organiser-authored prompt as the
// header). Question headers come from the form's question list
// rather than the summary's so empty forms don't crash here.
function csvEscape(v: unknown): string {
  const s = String(v ?? "");
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

async function downloadCsv() {
  if (!form.value) return;
  try {
    const submissions = await fetchFormSubmissions(props.formId);
    const questions = form.value.questions ?? [];
    const ids = questions.map((q) => q.id);
    const prompts = questions.map((q) => q.prompt);
    const header = [
      t("forms.details.csvSubmissionId"),
      t("forms.details.csvSubmittedAt"),
      ...prompts,
    ];
    const rows = submissions.map((s) => [
      s.submission_id,
      s.created_at,
      ...ids.map((id) => {
        const v = s.answers[id];
        return Array.isArray(v) ? v.join("; ") : (v ?? "");
      }),
    ]);
    const csv = [header, ...rows].map((r) => r.map(csvEscape).join(",")).join("\n");
    const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filenameSlug(form.value.name)}-${form.value.id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toasts.error(t("forms.details.csvFail"));
  }
}

function bar(distribution: number[], idx: number): { width: string; count: number } {
  const max = Math.max(...distribution, 1);
  return { width: `${Math.round((distribution[idx] / max) * 100)}%`, count: distribution[idx] };
}
</script>

<template>
  <DetailsPageShell :loaded="!!form" :skeleton-rows="4">
    <template v-if="form">
      <AppCard :stack="false" class="overview">
        <h1>
          {{ form.name }}
          <span v-if="form.chapter_name" class="chip">{{ form.chapter_name }}</span>
        </h1>
        <div class="link-row">
          <a :href="publicFormUrl(form.slug)" target="_blank" rel="noopener">
            {{ publicFormUrl(form.slug) }}
          </a>
          <Button
            icon="pi pi-copy"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('forms.details.copyLink')"
            :aria-label="t('forms.details.copyLink')"
            @click="copyLink"
          />
        </div>
        <div>
          <router-link :to="`/forms/${form.id}/edit`">
            <Button :label="t('common.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
          </router-link>
        </div>
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("forms.details.responsesTitle") }}</h2>
          <div class="header-actions">
            <Button
              :label="t('forms.details.exportCsv')"
              size="small"
              severity="secondary"
              text
              icon="pi pi-download"
              :disabled="!summary || summary.submission_count === 0"
              @click="downloadCsv"
            />
            <div v-if="summary" class="count-pill">
              <span class="count">{{ summary.submission_count }}</span>
              <span class="label">{{ t("forms.details.responses") }}</span>
            </div>
          </div>
        </div>

        <p v-if="!summary || summary.submission_count === 0" class="muted">
          {{ t("forms.details.noResponsesYet") }}
        </p>

        <template v-else>
          <div v-for="q in summary.questions" :key="q.id" class="q-block">
            <p class="q-prompt">{{ q.prompt }}</p>

            <template v-if="q.kind === 'rating' && q.rating_distribution">
              <p class="muted q-meta">
                {{ t("forms.details.qResponses", { n: q.response_count }) }}
                <template v-if="q.rating_average">
                  · {{ t("forms.details.qAverage", { avg: q.rating_average.toFixed(1) }) }}
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

            <template v-else-if="q.kind === 'text' || q.kind === 'short_text'">
              <p v-if="!q.texts || q.texts.length === 0" class="muted q-meta">
                {{ t("forms.details.noTextResponses") }}
              </p>
              <ul v-else class="texts">
                <li v-for="(txt, i) in q.texts" :key="i">{{ txt }}</li>
              </ul>
            </template>

            <template v-else-if="(q.kind === 'single_choice' || q.kind === 'multi_choice') && q.choice_counts">
              <p class="muted q-meta">{{ t("forms.details.qResponses", { n: q.response_count }) }}</p>
              <div class="bars">
                <div v-for="(count, label) in q.choice_counts" :key="label" class="bar-row">
                  <span class="bar-label choice-label">{{ label }}</span>
                  <div class="bar-track">
                    <div
                      class="bar-fill"
                      :style="{ width: q.response_count > 0 ? `${Math.round((count / q.response_count) * 100)}%` : '0%' }"
                    />
                  </div>
                  <span class="bar-count">{{ count }}</span>
                </div>
              </div>
            </template>
          </div>
        </template>
      </AppCard>
    </template>
  </DetailsPageShell>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.overview h1 {
  margin: 0;
  overflow-wrap: anywhere;
}
.chip {
  display: inline-flex;
  align-items: center;
  margin-left: 0.5rem;
  padding: 0.125rem 0.625rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.875rem;
  font-weight: 400;
  vertical-align: middle;
  white-space: nowrap;
}
.link-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
}
.link-row a {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.count-pill {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.125rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
  background: var(--brand-bg);
  min-width: 5rem;
}
.count-pill .count {
  font-weight: 700;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--brand-red);
}
.count-pill .label {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
}

.q-block {
  border-top: 1px solid var(--brand-border);
  padding-top: 1.5rem;
  margin-top: 1.5rem;
}
.q-block:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}
.q-prompt { margin: 0 0 0.5rem; font-weight: 600; }
.q-meta { margin: 0 0 0.5rem; }
.bars { display: flex; flex-direction: column; gap: 0.25rem; }
.bar-row {
  display: grid;
  grid-template-columns: minmax(1.25rem, max-content) 1fr 2.5rem;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
.bar-label { color: var(--brand-text-muted); }
.choice-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar-track {
  height: 0.625rem;
  background: var(--brand-border);
  border-radius: 999px;
  overflow: hidden;
}
.bar-fill { height: 100%; background: var(--brand-red); border-radius: 999px; }
.bar-count { text-align: right; color: var(--brand-text-muted); }
.texts {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.texts li { line-height: 1.45; }
</style>
