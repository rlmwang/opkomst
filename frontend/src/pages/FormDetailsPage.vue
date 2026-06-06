<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import { ApiError } from "@/api/client";
import { useFormClipboard } from "@/composables/useFormClipboard";
import {
  fetchFormSubmissions,
  useForm,
  useFormSummary,
} from "@/composables/useForms";
import { filenameSlug } from "@/lib/filename-slug";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ formId: string }>();

const { t } = useI18n();
const toasts = useToasts();
const { copyLink, copyQr } = useFormClipboard();

const formQuery = useForm(computed(() => props.formId));
const form = computed(() => formQuery.data.value ?? null);

// ``loaded`` flips true once the query has resolved either way —
// data OR error. Without this the page would sit on the
// skeleton forever for a bad / deleted form id.
const loaded = computed(() => !formQuery.isPending.value);

// Distinguish "form genuinely doesn't exist for this organiser"
// (404 — wrong chapter, wrong id, or deleted) from a generic
// fetch failure (network blip, 5xx). The first state gets a
// dedicated "not found" card; the second falls back to a
// generic message.
const notFound = computed(
  () => formQuery.error.value instanceof ApiError && formQuery.error.value.status === 404,
);
const otherError = computed(
  () => formQuery.error.value && !(notFound.value),
);

const summaryQuery = useFormSummary(computed(() => props.formId));
const summary = computed(() => summaryQuery.data.value ?? null);

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

/** Bar fill width as a percentage. The denominator is the
 *  maximum value in the block, NOT the sum — so the tallest bar
 *  always renders fully filled and the rest are visually
 *  proportional to it. For rating questions ``values`` is the
 *  per-bucket distribution; for choice questions it's the per-
 *  option count list. Same call shape across kinds keeps the
 *  template body symmetric. */
function barWidth(values: number[], value: number): string {
  const max = Math.max(...values, 1);
  return `${Math.round((value / max) * 100)}%`;
}
</script>

<template>
  <DetailsPageShell :loaded="loaded" :skeleton-rows="4">
    <AppCard v-if="notFound" :stack="false">
      <h2>{{ t("forms.details.notFoundTitle") }}</h2>
      <p class="muted">{{ t("forms.details.notFoundBody") }}</p>
      <router-link to="/forms" class="back-link">{{ t("forms.details.backToList") }}</router-link>
    </AppCard>

    <AppCard v-else-if="otherError" :stack="false">
      <p>{{ t("forms.details.loadFailed") }}</p>
    </AppCard>

    <template v-else-if="form">
      <!-- Overview card mirrors ``EventDetailsPage``: title row,
           body grid with text on the left (public URL + copy +
           edit) and the QR thumbnail on the right (clickable to
           copy the QR PNG to the clipboard). -->
      <AppCard :stack="false" class="overview">
        <h1>
          {{ form.name }}
          <span v-if="form.chapter_name" class="chip">{{ form.chapter_name }}</span>
        </h1>
        <div class="overview-body">
          <div class="overview-text">
            <div class="link-row">
              <a :href="publicFormUrl(form.slug)" target="_blank" rel="noopener">
                {{ publicFormUrl(form.slug) }}
              </a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                v-tooltip.top="t('forms.share.copyLink')"
                :aria-label="t('forms.share.copyLink')"
                @click="copyLink(form.slug)"
              />
            </div>
            <div>
              <router-link :to="`/forms/${form.id}/edit`">
                <Button :label="t('common.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
              </router-link>
            </div>
          </div>
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('forms.share.copyQr')"
            :aria-label="t('forms.share.copyQr')"
            @click="copyQr(form.slug)"
          >
            <img :src="formQrUrl(form.slug)" alt="" class="qr" />
          </button>
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
              <!-- ``.bars`` is the single grid container so all
                   bar tracks within a block share the same width
                   (label + count columns auto-size to the widest
                   entry across the whole block, then ``1fr``
                   for the track makes every bar the same length).
                   Label / track / count are direct grid items
                   (no per-row wrapper). -->
              <div class="bars">
                <template v-for="i in 5" :key="i">
                  <span class="bar-label">{{ i }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: barWidth(q.rating_distribution, q.rating_distribution[i - 1]) }" />
                  </div>
                  <span class="bar-count">{{ q.rating_distribution[i - 1] }}</span>
                </template>
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
                <template v-for="(count, label) in q.choice_counts" :key="label">
                  <span class="bar-label choice-label">{{ label }}</span>
                  <div class="bar-track">
                    <div
                      class="bar-fill"
                      :style="{ width: barWidth(Object.values(q.choice_counts), count) }"
                    />
                  </div>
                  <span class="bar-count">{{ count }}</span>
                </template>
              </div>
            </template>
          </div>
        </template>
      </AppCard>
    </template>
  </DetailsPageShell>
</template>

<style scoped>
.back-link {
  display: inline-block;
  margin-top: 0.5rem;
  color: var(--brand-red);
}
/* Mirrors ``EventDetailsPage``'s overview card: title row + a
 * ``overview-body`` grid with ``1fr auto`` so the QR sits flush
 * right and the text wraps to fill the left column. Below
 * 480px the QR drops underneath the text (same breakpoint the
 * event page uses). */
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
.overview-body {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1rem;
  align-items: start;
}
.overview-text {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
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
.qr-button {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  flex-shrink: 0;
}
.qr-button:focus-visible {
  outline: 2px solid var(--brand-red);
  outline-offset: 2px;
  border-radius: 8px;
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 0.375rem;
  display: block;
}
@media (max-width: 480px) {
  .overview-body {
    grid-template-columns: 1fr;
  }
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
/* One grid per question block — the label column auto-sizes to
 * the widest entry IN THIS BLOCK and every track gets the same
 * remaining ``1fr`` width. That gives the two visual guarantees
 * the data needs: bars are comparable within a question (same
 * length), and the tallest bar fully fills (denominator is the
 * max in the block, not the response count). */
.bars {
  display: grid;
  grid-template-columns: minmax(1.25rem, max-content) 1fr 2.5rem;
  align-items: center;
  gap: 0.375rem 0.5rem;
  font-size: 0.875rem;
}
.bar-label { color: var(--brand-text-muted); }
.choice-label {
  /* Long option labels wrap rather than ellipsis-truncate — the
   * organiser wrote them, the respondent picked them, and
   * hiding part of a label undermines what the bar is showing. */
  overflow-wrap: anywhere;
  max-width: 14rem;
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
