<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import AppCard from "@/components/AppCard.vue";
import DetailHeaderCard from "@/components/DetailHeaderCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.vue";
import CompassPlot from "@/public_shared/CompassPlot.vue";
import StatBar from "@/components/StatBar.vue";
import { ApiError } from "@/api/client";
import { useFormClipboard } from "@/composables/useFormClipboard";
import { type FormOut, useFormsApi } from "@/composables/useForms";
import { useFormText } from "@/composables/useFormText";
import { downloadCsv } from "@/lib/csv-export";
import { filenameSlug } from "@/lib/filename-slug";
import { barWidth, formatAverage, formatDecimal } from "@/lib/format";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ formId: string }>();
// A personal account holds a bounded number of people per form; an
// organisation has no ceiling, so the pill shows the bare count.
const auth = useAuthStore();

const { t, locale } = useI18n();
const lt = useLocalizedText();
const toasts = useToasts();
// One page, three products; the route says which (``useForms``).
const api = useFormsApi();
const { L, isQuiz: quizProduct, isCompass: compassProduct } = useFormText();
const isQuiz = computed(() => quizProduct);
const isCompass = computed(() => compassProduct);
const { copyLink, copyQr } = useFormClipboard(api.resource);
const publicPageUrl = (slug: string) => publicFormUrl(api.resource, slug);
const qrSrc = (slug: string) => formQrUrl(api.resource, slug);
type Question = NonNullable<FormOut["questions"]>[number];

/** The kompas half of the summary, or null on the other two products
 *  (``docs/design-kompas.md`` 4.5). */
const compass = computed(() => summary.value?.compass ?? null);

/** One side of one axis, in the organiser's own words: the label every
 *  count and every statement on this page is read next to. Falls back
 *  to the bare token only if a kompas somehow saved without its axes,
 *  which the server refuses. */
function poleName(pole: string | null | undefined): string {
  if (!pole) return "";
  const [axis, side] = pole.split("_");
  const row = compass.value?.axes.find((a) => a.axis.axis === axis)?.axis ?? form.value?.axes?.find((a) => a.axis === axis);
  if (!row) return pole;
  return `${row.name}: ${side === "low" ? row.low_name : row.high_name}`;
}

/** Which way one option of a choice question pushed. The poles are
 *  index-parallel to the options, which is how the two arrive, and the
 *  options are on the form's own question list: an aggregate row
 *  carries the counts and not the order they were written in. */
const questionById = computed(
  () => new Map((form.value?.questions ?? []).map((q) => [q.id, q])),
);

function optionPoleName(questionId: string, option: string): string {
  const question = questionById.value.get(questionId);
  const index = (question?.options ?? []).indexOf(option);
  return index < 0 ? "" : poleName(question?.option_poles?.[index]);
}

/** The same direction, in one word rather than two. Read on a counted
 *  row next to the option itself, where the axis it belongs to is
 *  already the subject of the question and is spelled out in full in
 *  the axes overview above. */
function optionPoleSide(questionId: string, option: string): string {
  const question = questionById.value.get(questionId);
  const index = (question?.options ?? []).indexOf(option);
  const pole = index < 0 ? null : question?.option_poles?.[index];
  if (!pole) return "";
  const [axis, side] = pole.split("_");
  const row =
    compass.value?.axes.find((a) => a.axis.axis === axis)?.axis ?? form.value?.axes?.find((a) => a.axis === axis);
  if (!row) return pole;
  return side === "low" ? row.low_name : row.high_name;
}

/** A rating's average restated as what it was worth on its axis: the
 *  same arithmetic ``services/compass.contribution`` runs, so the page
 *  and the map cannot disagree about which way the room leaned. */
function ratingContribution(average: number, pole: string): string {
  return formatDecimal(Math.round(((average - 3) / 2) * (pole.endsWith("_high") ? 1 : -1) * 100) / 100, locale.value);
}

/** What a number question accepts, in one line: the same rule the
 *  person answering it reads under the box. */
function numberRule(q: Question): string | null {
  const parts: string[] = [];
  if (q.step && q.step > 1) parts.push(t("forms.details.ruleStep", { step: q.step }));
  if (q.min_value !== null && q.min_value !== undefined && q.max_value !== null && q.max_value !== undefined) {
    parts.push(t("forms.details.ruleBetween", { min: q.min_value, max: q.max_value }));
  } else if (q.min_value !== null && q.min_value !== undefined) {
    parts.push(t("forms.details.ruleFrom", { min: q.min_value }));
  } else if (q.max_value !== null && q.max_value !== undefined) {
    parts.push(t("forms.details.ruleUpTo", { max: q.max_value }));
  }
  if (isQuiz.value && q.tolerance) parts.push(t("quizzes.details.ruleMargin", { margin: q.tolerance }));
  return parts.length ? parts.join(", ") : null;
}

/** Is this option the right answer? Only a quiz has one. */
function isKeyOption(q: Question, option: string): boolean {
  return isQuiz.value && (q.correct_choices ?? []).includes(option);
}

/** The right answer for the kinds that do not list their options. */
function typedKey(q: Question): string | null {
  if (!isQuiz.value || q.points <= 0) return null;
  if (q.kind === "number" || q.kind === "rating") return q.correct_int === null ? null : String(q.correct_int);
  return null;
}

const formQuery = api.useSingle(computed(() => props.formId));
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

const summaryQuery = api.useSummary(computed(() => props.formId));
const summary = computed(() => summaryQuery.data.value ?? null);

// Rows for the responses pill's recovery popover.
async function recoverRows(): Promise<RecoverableRow[]> {
  const subs = await api.fetchSubmissions(props.formId);
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
    const submissions = await api.fetchSubmissions(props.formId);
    const questions = form.value.questions ?? [];
    const ids = questions.map((q) => q.id);
    const prompts = questions.map((q) => q.prompt);
    const header = [
      L("details.csvName"),
      L("details.csvSubmittedAt"),
      // A kompas's two derived columns, next to the answers that
      // produced them.
      ...(isCompass.value ? ["x", "y"] : []),
      ...prompts,
    ];
    const rows = submissions.map((s) => [
      s.display_name ?? L("details.anonymous"),
      s.created_at,
      ...(isCompass.value ? [s.x ?? "", s.y ?? ""] : []),
      ...ids.map((id) => {
        const v = s.answers[id];
        return Array.isArray(v) ? v.join("; ") : (v ?? "");
      }),
    ]);
    downloadCsv(`${filenameSlug(lt(form.value.name_nl, form.value.name_en) ?? "")}-${form.value.id}.csv`, [header, ...rows]);
  } catch {
    toasts.error(L("details.csvFail"));
  }
}
</script>

<template>
  <DetailsPageShell :loaded="loaded" :skeleton-rows="4">
    <AppCard v-if="notFound" :stack="false">
      <h2>{{ L("details.notFoundTitle") }}</h2>
      <p class="muted">{{ L("details.notFoundBody") }}</p>
      <router-link :to="`/${api.resource}`" class="back-link">{{ L("details.backToList") }}</router-link>
    </AppCard>

    <AppCard v-else-if="otherError" :stack="false">
      <p>{{ L("details.loadFailed") }}</p>
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
        :qr-src="qrSrc(form.slug)"
        :public-url="publicPageUrl(form.slug)"
        :edit-to="`/${api.resource}/${form.id}/edit`"
        @copy-qr="copyQr(form.slug)"
        @copy-link="copyLink(form.slug)"
      />

      <!-- Kompas only: what the two axes are and what each side of them
           is called. Every pole named further down this page is one of
           these four words, so the page says them once, above the
           questions that place people on them, rather than sending the
           organiser to the editor to look them up. -->
      <AppCard v-if="isCompass && (form.axes ?? []).length">
        <div class="summary-header">
          <h2>{{ t("compasses.details.axesHeading") }}</h2>
        </div>
        <ul class="axis-defs">
          <li v-for="axis in form.axes ?? []" :key="axis.axis">
            <span class="axis-def-name">{{ axis.name }}</span>
            <span v-if="axis.description" class="muted axis-def-desc">{{ axis.description }}</span>
            <span class="muted axis-def-poles">{{ axis.low_name }} &middot; {{ axis.high_name }}</span>
          </li>
        </ul>
      </AppCard>

      <!-- Defined questions overview — the questionnaire's structure,
           shown independently of any responses (mirrors the chore
           details "Taken" card listing the defined chores). -->
      <AppCard v-if="form.questions?.length">
        <div class="summary-header">
          <h2>{{ L("details.questionsHeading") }}</h2>
        </div>
        <ol class="q-overview">
          <li v-for="q in form.questions ?? []" :key="q.id" class="q-overview-item">
            <div class="q-overview-head">
              <span class="q-overview-prompt">{{ q.prompt }}</span>
              <span class="q-overview-kind">{{ t(`forms.details.kind.${q.kind}`) }}</span>
            </div>
            <!-- What this question accepts, for the kind whose answer
                 is typed rather than picked. The same line the person
                 answering it reads. -->
            <p v-if="q.kind === 'number' && numberRule(q)" class="muted q-overview-rule">
              {{ numberRule(q) }}
            </p>
            <!-- The options, with the right one marked on a quiz: an
                 overview that cannot say which answer was right is one
                 an organiser has to open the editor to read. -->
            <!-- On a kompas the direction is what the option means, so
                 it is read on the same row rather than looked up
                 elsewhere. -->
            <p v-if="isCompass && q.kind === 'rating' && q.pole" class="muted q-overview-rule">
              {{ t("compasses.details.ratingPole", { pole: poleName(q.pole) }) }}
            </p>
            <ul v-if="q.options.length" class="q-overview-options">
              <li v-for="o in q.options" :key="o" :class="{ 'is-key': isKeyOption(q, o) }">
                {{ o }}<template v-if="isCompass">
                  <span class="option-pole">{{ optionPoleName(q.id, o) }}</span>
                </template>
              </li>
            </ul>
            <p v-if="typedKey(q)" class="muted q-overview-rule">
              {{ t("quizzes.details.rightAnswerIs", { answer: typedKey(q) }) }}
            </p>
          </li>
        </ol>
      </AppCard>

      <!-- Kompas only: what the answers add up to, under the overview
           of what was asked, the same order every other product's
           details page reads in. No dot is ringed here, because on the
           organiser's page nobody is "you". -->
      <AppCard v-if="isCompass && compass">
        <div class="summary-header">
          <h2>{{ t("compasses.details.mapHeading") }}</h2>
        </div>
        <p v-if="!compass.points.length" class="muted">{{ t("compasses.details.noPositions") }}</p>
        <template v-else>
          <CompassPlot
            :axes="compass.axes.map((a) => a.axis)"
            :points="compass.points"
            :anonymous-label="L('details.anonymous')"
            :aria-label="t('compasses.details.mapHeading')"
          />
          <!-- Where the room sits on each axis. Not a histogram: the
               coordinates are means of a handful of values, so a bar
               chart of them would be a picture of the question count.
               -->
          <div class="axis-stats">
            <div v-for="row in compass.axes" :key="row.axis.axis" class="axis-stat">
              <p class="axis-stat-name">{{ row.axis.name }}</p>
              <p v-if="row.axis.description" class="muted q-meta">{{ row.axis.description }}</p>
              <!-- The bar is the axis, so it runs the full width and
                   the two side names sit under its ends: a name beside
                   the track shortens it by however long that word is,
                   and the two axes then draw at different lengths. -->
              <div class="axis-track">
                <span class="axis-bar">
                  <!-- How sure the mean is, drawn behind it: a room
                       that agrees and a room that is split do not
                       draw the same. -->
                  <span
                    v-if="row.ci_low != null && row.ci_high != null"
                    class="axis-spread"
                    :style="{
                      left: `${((row.ci_low! + 1) / 2) * 100}%`,
                      width: `${((row.ci_high! - row.ci_low!) / 2) * 100}%`,
                    }"
                  />
                  <span
                    v-if="row.average != null"
                    class="axis-marker"
                    :style="{ left: `${((row.average! + 1) / 2) * 100}%` }"
                  />
                </span>
              </div>
              <div class="axis-ends-row muted">
                <span>{{ row.axis.low_name }}</span>
                <span class="axis-end-right">{{ row.axis.high_name }}</span>
              </div>
              <p v-if="row.average !== null && row.average !== undefined" class="muted q-meta">
                {{
                  t("compasses.details.interval", {
                    avg: formatDecimal(row.average!, locale),
                    low: formatDecimal(row.ci_low!, locale),
                    high: formatDecimal(row.ci_high!, locale),
                  })
                }}
              </p>
            </div>
          </div>
        </template>
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ L("details.responsesTitle") }}</h2>
          <div class="header-actions">
            <AppButton
              :label="L('details.exportCsv')"
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
              :cap="auth.user?.participant_cap ?? null"
              :label="L('details.responses')"
              :load-rows="recoverRows"
              :recover-path="(id: string) => `/api/v1/${api.resource}/${props.formId}/submissions/${id}/edit-link`"
              :public-url="(tok: string) => `${publicPageUrl(form!.slug)}?s=${tok}`"
            />
          </div>
        </div>

        <p v-if="!summary || summary.submission_count === 0" class="muted">
          {{ L("details.noResponsesYet") }}
        </p>

        <template v-else>
          <!-- Quiz only: how the room did, above the per-question
               breakdown that says which question it was that did for
               them. Its own element rather than a branch of the
               chain, or it takes the breakdown's place. -->
          <p
            v-if="isQuiz && summary.score_average !== null && summary.score_average !== undefined"
            class="muted q-meta score-line"
          >
            {{
              t("quizzes.details.scoreLine", {
                avg: summary.score_average,
                best: summary.score_best,
                max: summary.max_score,
              })
            }}
          </p>

          <div v-for="q in summary.questions" :key="q.id" class="q-block">
            <p class="q-prompt">{{ q.prompt }}</p>
            <!-- The one aggregate a quiz has that a survey cannot: the
                 share who got it right, which is what says a question
                 was broken rather than hard. -->
            <p v-if="q.correct_share !== null && q.correct_share !== undefined" class="muted q-meta">
              {{ t("quizzes.details.correctShare", { pct: Math.round(q.correct_share * 100) }) }}
            </p>

            <template v-if="q.kind === 'rating' && q.rating_distribution">
              <p class="muted q-meta">
                {{ t("forms.details.qResponses", { n: q.response_count }) }}
                <template v-if="q.rating_average">
                  · {{ t("forms.details.qAverage", { avg: formatAverage(q.rating_average, locale) }) }}
                </template>
              </p>
              <!-- The average restated as what it was worth: "3,8 van 5"
                   says how people answered, and "0,4 richting Links"
                   says what it did to the map. -->
              <p v-if="isCompass && q.pole && q.rating_average" class="muted q-meta">
                {{
                  t("compasses.details.ratingContribution", {
                    avg: formatAverage(q.rating_average, locale),
                    value: ratingContribution(q.rating_average, q.pole),
                    pole: poleName(q.pole),
                  })
                }}
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

            <!-- Four numbers rather than a chart: the buckets for an
                 arbitrary range are a choice with no obvious right
                 answer, and "what did people say" for an age or a
                 headcount is answered by these (docs/design-quizzes.md
                 part 2). The raw values are in the CSV. -->
            <template v-else-if="q.kind === 'number'">
              <p class="muted q-meta">
                {{ L("details.qResponses", { n: q.response_count }) }}
                <template v-if="q.number_average !== null && q.number_average !== undefined">
                  · {{ t("forms.details.qAverage", { avg: formatAverage(q.number_average, locale) }) }}
                  · {{ t("forms.details.qRange", { low: q.number_min, high: q.number_max }) }}
                </template>
              </p>
              <!-- One bar per allowed value while the question's own
                   bounds and step leave few of them, binned past that
                   (``services/numbers``). Same bar track as the rating
                   and choice aggregates, so the three read alike. -->
              <div v-if="q.number_buckets?.length" class="bars">
                <template v-for="bucket in q.number_buckets" :key="bucket.label">
                  <span class="bar-label">{{ bucket.label }}</span>
                  <StatBar :segments="[{ width: barWidth(q.number_buckets.map((b) => b.count), bucket.count) }]" />
                  <span class="bar-count">{{ bucket.count }}</span>
                </template>
              </div>
            </template>

            <template v-else-if="q.kind === 'text' || q.kind === 'short_text'">
              <p v-if="!q.texts || q.texts.length === 0" class="muted q-meta">
                {{ L("details.noTextResponses") }}
              </p>
              <ul v-else class="texts">
                <li v-for="(txt, i) in q.texts" :key="i">{{ txt }}</li>
              </ul>
            </template>

            <template v-else-if="(q.kind === 'single_choice' || q.kind === 'multi_choice') && q.choice_counts">
              <p class="muted q-meta">{{ t("forms.details.qResponses", { n: q.response_count }) }}</p>
              <div class="bars">
                <template v-for="(count, label) in q.choice_counts" :key="label">
                  <span class="bar-label choice-label">
                    <!-- The option's own words, and on a kompas the
                         side it pushed toward, held to the right so
                         the poles line up down the block. The axis is
                         named once in the overview above, so the row
                         carries the side and not both. -->
                    <span class="choice-text" :title="String(label)">{{ label }}</span>
                    <span v-if="isCompass" class="option-pole">{{ optionPoleSide(q.id, String(label)) }}</span>
                  </span>
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
/* The overview card is ``DetailHeaderCard`` and owns its own layout;
 * ``.overview-meta`` and the .summary-header / .header-actions row come
 * from theme.css. */

/* Kompas: the map card's two axis readouts. */
.axis-stats {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 1.25rem;
}
.axis-stat-name {
  margin: 0;
  font-weight: 600;
}
.axis-track {
  display: flex;
  align-items: center;
  margin: 0.375rem 0;
}
/* Both side names under the track's own ends, which is what keeps the
 * two axes the same length as each other. Same shape as the
 * respondent's result page (``public_compass/PublicCompass.vue``). */
.axis-ends-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.8125rem;
}
.axis-end-right {
  text-align: right;
}
.axis-bar {
  position: relative;
  flex: 1 1 auto;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--brand-border);
}
.axis-spread {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 999px;
  background: var(--brand-red);
  opacity: 0.28;
  /* A room that all answered the same has no width to draw, so it
   * still gets a sliver rather than disappearing under the marker. */
  min-width: 2px;
}
.axis-marker {
  position: absolute;
  top: -0.125rem;
  width: 0.25rem;
  height: 0.75rem;
  margin-left: -0.125rem;
  border-radius: 2px;
  background: var(--brand-red);
}
/* The direction an option or a statement carried, read on the same
 * row as the thing it belongs to. */
.option-pole {
  margin-left: 0.5rem;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}

/* Kompas: what the two axes are, above the questions that place
 * people on them. */
.axis-defs {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.axis-def-name {
  font-weight: 600;
}
.axis-def-desc,
.axis-def-poles {
  margin-left: 0.5rem;
  font-size: 0.8125rem;
}

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
.q-overview-rule {
  margin: 0.125rem 0 0;
  font-size: 0.8125rem;
}
/* The right answer, marked where the options are listed. */
.q-overview-options li.is-key {
  background: var(--brand-green-soft);
  border-color: var(--brand-green);
  color: var(--brand-text);
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
.score-line {
  margin-bottom: 1rem;
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
  /* Option on the left, the side it pushed toward on the right, so the
   * poles read as a column down the block. A long option is clipped
   * rather than wrapped: a label two lines tall pushes its own bar out
   * of line with the ones above it, and the full text is on the
   * element's title. */
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  max-width: 18rem;
}
.choice-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.choice-label .option-pole {
  margin-left: auto;
  flex: 0 0 auto;
  text-align: right;
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
