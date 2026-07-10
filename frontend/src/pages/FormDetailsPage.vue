<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import AppCard from "@/components/AppCard.vue";
import DetailHeaderCard from "@/components/DetailHeaderCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.vue";
import StatBar from "@/components/StatBar.vue";
import { ApiError } from "@/api/client";
import { useFormClipboard } from "@/composables/useFormClipboard";
import {
  fetchFormSubmissions,
  useForm,
  useFormSummary,
} from "@/composables/useForms";
import { downloadCsv } from "@/lib/csv-export";
import { filenameSlug } from "@/lib/filename-slug";
import { barWidth } from "@/lib/format";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ formId: string }>();

const { t } = useI18n();
const lt = useLocalizedText();
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

// Rows for the responses pill's recovery popover.
async function recoverRows(): Promise<RecoverableRow[]> {
  const subs = await fetchFormSubmissions(props.formId);
  return subs.map((s) => ({ id: s.submission_id, name: s.display_name, recoveredAt: s.link_recovered_at ?? null }));
}

// --- CSV export ---------------------------------------------------
// One row per submission. Columns: submission id + submission
// time + one per question (organiser-authored prompt as the
// header). Question headers come from the form's question list
// rather than the summary's so empty forms don't crash here.
async function exportCsv() {
  if (!form.value) return;
  try {
    const submissions = await fetchFormSubmissions(props.formId);
    const questions = form.value.questions ?? [];
    const ids = questions.map((q) => q.id);
    const prompts = questions.map((q) => q.prompt);
    const header = [
      t("forms.details.csvName"),
      t("forms.details.csvSubmittedAt"),
      ...prompts,
    ];
    const rows = submissions.map((s) => [
      s.display_name ?? t("forms.details.anonymous"),
      s.created_at,
      ...ids.map((id) => {
        const v = s.answers[id];
        return Array.isArray(v) ? v.join("; ") : (v ?? "");
      }),
    ]);
    downloadCsv(`${filenameSlug(lt(form.value.name_nl, form.value.name_en) ?? "")}-${form.value.id}.csv`, [header, ...rows]);
  } catch {
    toasts.error(t("forms.details.csvFail"));
  }
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
      <DetailHeaderCard
        :title="lt(form.name_nl, form.name_en) ?? ''"
        :chapter-name="form.chapter_name"
        :image-url="form.image_url"
        :image-artist="form.image_artist_instagram"
        :description-html="lt(form.description_nl, form.description_en)"
        :qr-src="formQrUrl(form.slug)"
        :public-url="publicFormUrl(form.slug)"
        :edit-to="`/forms/${form.id}/edit`"
        @copy-qr="copyQr(form.slug)"
        @copy-link="copyLink(form.slug)"
      />

      <!-- Defined questions overview — the questionnaire's structure,
           shown independently of any responses (mirrors the chore
           details "Taken" card listing the defined chores). -->
      <AppCard v-if="form.questions?.length">
        <div class="summary-header">
          <h2>{{ t("forms.details.questionsHeading") }}</h2>
        </div>
        <ol class="q-overview">
          <li v-for="q in form.questions ?? []" :key="q.id" class="q-overview-item">
            <div class="q-overview-head">
              <span class="q-overview-prompt">{{ q.prompt }}</span>
              <span class="q-overview-kind">{{ t(`forms.details.kind.${q.kind}`) }}</span>
            </div>
            <ul v-if="q.options.length" class="q-overview-options">
              <li v-for="o in q.options" :key="o">{{ o }}</li>
            </ul>
          </li>
        </ol>
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
              @click="exportCsv"
            />
            <RecoverLinksPill
              v-if="summary && form"
              :count="summary.submission_count"
              :label="t('forms.details.responses')"
              :load-rows="recoverRows"
              :recover-path="(id: string) => `/api/v1/forms/${props.formId}/submissions/${id}/edit-link`"
              :public-url="(tok: string) => `${publicFormUrl(form!.slug)}?s=${tok}`"
            />
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
                  <StatBar :segments="[{ width: barWidth(q.rating_distribution, q.rating_distribution[i - 1]) }]" />
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
                  <StatBar :segments="[{ width: barWidth(Object.values(q.choice_counts), count) }]" />
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
/* The overview card (.overview*, .detail-image, .qr*) and the
 * .summary-header / .header-actions row are shared from theme.css. */

/* Defined-questions overview card: one row per question — the prompt with
 * a small kind label, plus the choice options as pills. */
.q-overview {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.q-overview-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.q-overview-head {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.q-overview-prompt {
  font-weight: 600;
}
.q-overview-kind {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--brand-text-muted);
}
.q-overview-options {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}
.q-overview-options li {
  font-size: 0.8125rem;
  padding: 0.125rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-bg);
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
.bar-count { text-align: right; color: var(--brand-text-muted); }
.texts {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.texts li { line-height: 1.45; white-space: pre-line; }
</style>
