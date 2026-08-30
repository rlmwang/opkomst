<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import DetailHeaderCard from "@/components/DetailHeaderCard.svelte";
import DetailsPageShell from "@/components/DetailsPageShell.svelte";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.svelte";
import StatBar from "@/components/StatBar.svelte";
import CompassPlot from "@/public_shared/CompassPlot.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { type FormOut, formsApi } from "@/composables/useForms.svelte";
import { formText } from "@/composables/useFormText.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { locale, t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { downloadFile } from "@/lib/download";
import { barWidth, formatAverage, formatDecimal } from "@/lib/format";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";

/**
 * What a questionnaire, a quiz or a kompas came back with.
 *
 * One page for the three products: what was asked, and then what the
 * answers add up to. The quiz adds a score and a share who got each
 * question right; the kompas adds its two axes, a map of where people
 * landed, and the direction every option pushed.
 */
const { formId }: { formId: string } = $props();

const toasts = useToasts();
const api = formsApi();
const { L, isQuiz, isCompass } = formText();
const share = shareClipboard({
  publicUrlFor: (slug) => publicFormUrl(api.resource, slug),
  qrUrlFor: (slug) => formQrUrl(api.resource, slug),
  copyPrefix: "form.share",
});

type Question = NonNullable<FormOut["questions"]>[number];

const query = api.single(() => formId);
const form = $derived(query.data ?? null);

// A form that genuinely is not this organiser's (wrong chapter, wrong
// id, deleted) gets its own card; anything else is a fetch that failed
// and says so generically.
const notFound = $derived(query.error instanceof ApiError && query.error.status === 404);

const summaryQuery = api.summary(() => formId);
const summary = $derived(summaryQuery.data ?? null);

/** The kompas half of the summary, null on the other two products. */
const compass = $derived(summary?.compass ?? null);

/** One side of one axis, in the organiser's own words: the label every
 *  count and every statement here is read against. Falls back to the
 *  bare token only for a kompas saved without its axes, which the
 *  server refuses. */
function poleName(pole: string | null | undefined): string {
  if (!pole) return "";
  const [axis, side] = pole.split("_");
  const row =
    compass?.axes.find((a) => a.axis.axis === axis)?.axis ??
    form?.axes?.find((a) => a.axis === axis);
  if (!row) return pole;
  return `${row.name}: ${side === "low" ? row.low_name : row.high_name}`;
}

/** Which way one option pushed. The poles are index-parallel to the
 *  options, which is how the two arrive, and the options live on the
 *  form's own question list: an aggregate row carries the counts, not
 *  the order they were written in. */
const questionById = $derived(new Map((form?.questions ?? []).map((q) => [q.id, q])));

function optionPoleName(questionId: string, label: string): string {
  const option = questionById.get(questionId)?.options?.find((o) => o.label === label);
  return poleName(option?.pole ?? null);
}

/** The same direction in one word instead of two. Read on a counted
 *  row, where the axis is already the subject of the question and is
 *  spelled out in full in the overview above. */
function optionPoleSide(questionId: string, label: string): string {
  const pole = questionById.get(questionId)?.options?.find((o) => o.label === label)?.pole;
  if (!pole) return "";
  const [axis, side] = pole.split("_");
  const row =
    compass?.axes.find((a) => a.axis.axis === axis)?.axis ??
    form?.axes?.find((a) => a.axis === axis);
  if (!row) return pole;
  return side === "low" ? row.low_name : row.high_name;
}

/** A rating's average restated as what it was worth on its axis. The
 *  same arithmetic ``services/compass.contribution`` runs, so this page
 *  and the map cannot disagree about which way the room leaned. */
function ratingContribution(average: number, pole: string): string {
  const value = ((average - 3) / 2) * (pole.endsWith("_high") ? 1 : -1);
  return formatDecimal(Math.round(value * 100) / 100, locale());
}

/** What a number question accepts, in one line: the same rule the
 *  person answering it reads under the box. */
function numberRule(q: Question): string | null {
  const parts: string[] = [];
  if (q.step && q.step > 1) parts.push(t("form.details.ruleStep", { step: q.step }));
  if (q.min_value != null && q.max_value != null) {
    parts.push(t("form.details.ruleBetween", { min: q.min_value, max: q.max_value }));
  } else if (q.min_value != null) {
    parts.push(t("form.details.ruleFrom", { min: q.min_value }));
  } else if (q.max_value != null) {
    parts.push(t("form.details.ruleUpTo", { max: q.max_value }));
  }
  if (isQuiz && q.tolerance) parts.push(t("quiz.details.ruleMargin", { margin: q.tolerance }));
  return parts.length ? parts.join(", ") : null;
}

/** Is this the right answer? Only a quiz has one, and it is a flag on
 *  the option rather than a list of labels beside it. */
function isKeyOption(q: Question, label: string): boolean {
  return isQuiz && (q.options ?? []).some((o) => o.label === label && o.is_correct);
}

/** The right answer for the kinds that list no options to mark. */
function typedKey(q: Question): string | null {
  if (!isQuiz || q.points <= 0) return null;
  if (q.kind === "number" || q.kind === "rating") {
    return q.correct_int === null ? null : String(q.correct_int);
  }
  return null;
}

/** The rows behind the responses pill's recovery popover. */
async function recoverRows(): Promise<RecoverableRow[]> {
  const subs = await api.fetchSubmissions(formId);
  return subs.map((s) => ({
    id: s.submission_id,
    name: s.display_name,
    recoveredAt: s.link_recovered_at ?? null,
  }));
}

/** The download. The server writes the file and names it; the page
 * only asks for it (``services/csv_export``). */
async function exportCsv(): Promise<void> {
  if (!form) return;
  try {
    await downloadFile(`/api/v1/${api.resource}/${formId}/submissions.csv`, `${form.id}.csv`);
  } catch {
    toasts.error(L("details.csvFail"));
  }
}
</script>

<DetailsPageShell loaded={!query.isPending} skeletonRows={4}>
  {#if notFound}
    <AppCard stack={false}>
      <h2>{L("details.notFoundTitle")}</h2>
      <p class="muted">{L("details.notFoundBody")}</p>
      <RouterLink to={`/${api.resource}`} class="back-link">{L("details.backToList")}</RouterLink>
    </AppCard>
  {:else if query.error}
    <AppCard stack={false}>
      <p>{L("details.loadFailed")}</p>
    </AppCard>
  {:else if form}
    {@const slug = form.slug}
    <DetailHeaderCard
      title={lt(form.name_nl, form.name_en) ?? ""}
      chapterName={form.chapter_name}
      imageUrl={form.image_url}
      imageArtist={form.image_artist_instagram}
      descriptionHtml={lt(form.description_nl, form.description_en)}
      qrSrc={formQrUrl(api.resource, slug)}
      publicUrl={publicFormUrl(api.resource, slug)}
      editTo={`/${api.resource}/${form.id}/edit`}
      oncopyQr={() => void share.copyQr(slug)}
      oncopyLink={() => void share.copyLink(slug)}
    />

    <!-- A kompas's two axes and what each side of them is called. Every
         direction named further down is one of these four words, so the
         page says them once, above the questions that place people on
         them, instead of sending the organiser to the editor. -->
    {#if isCompass && (form.axes ?? []).length}
      <AppCard>
        <div class="summary-header">
          <h2>{t("compass.details.axesHeading")}</h2>
        </div>
        <ul class="axis-defs">
          {#each form.axes ?? [] as axis (axis.axis)}
            <li>
              <span class="axis-def-name">{axis.name}</span>
              {#if axis.description}
                <span class="muted axis-def-desc">{axis.description}</span>
              {/if}
              <span class="muted axis-def-poles">{axis.low_name} · {axis.high_name}</span>
            </li>
          {/each}
        </ul>
      </AppCard>
    {/if}

    <!-- What was asked, shown whether or not anybody has answered. The
         same card the roster page gives its chores. -->
    {#if form.questions?.length}
      <AppCard>
        <div class="summary-header">
          <h2>{L("details.questionsHeading")}</h2>
        </div>
        <ol class="q-overview">
          {#each form.questions ?? [] as q (q.id)}
            <li class="q-overview-item">
              <div class="q-overview-head">
                <span class="q-overview-prompt">{q.prompt}</span>
                <span class="q-overview-kind">{t(`form.details.kind.${q.kind}`)}</span>
              </div>
              <!-- What a typed answer has to be, in the words the person
                   answering reads. -->
              {#if q.kind === "number" && numberRule(q)}
                <p class="muted q-overview-rule">{numberRule(q)}</p>
              {/if}
              <!-- On a kompas the direction is what the statement means,
                   so it is read on the same row. -->
              {#if isCompass && q.kind === "rating" && q.pole}
                <p class="muted q-overview-rule">
                  {t("compass.details.ratingPole", { pole: poleName(q.pole) })}
                </p>
              {/if}
              <!-- The options, with the right one marked on a quiz: an
                   overview that cannot say which answer was right is one
                   the organiser has to open the editor to read. -->
              {#if q.options.length}
                <ul class="q-overview-options">
                  {#each q.options as o (o.id)}
                    <li class:is-key={isKeyOption(q, o.label)}>
                      {o.label}{#if isCompass}<span class="option-pole"
                          >{optionPoleName(q.id, o.label)}</span
                        >{/if}
                    </li>
                  {/each}
                </ul>
              {/if}
              {#if typedKey(q)}
                <p class="muted q-overview-rule">
                  {t("quiz.details.rightAnswerIs", { answer: typedKey(q) })}
                </p>
              {/if}
            </li>
          {/each}
        </ol>
      </AppCard>
    {/if}

    <!-- What the answers add up to, under the overview of what was
         asked: the order every other details page reads in. No dot is
         ringed, because on the organiser's page nobody is "you". -->
    {#if isCompass && compass}
      <AppCard>
        <div class="summary-header">
          <h2>{t("compass.details.mapHeading")}</h2>
        </div>
        {#if !compass.points.length}
          <p class="muted">{t("compass.details.noPositions")}</p>
        {:else}
          <CompassPlot
            axes={compass.axes.map((a) => a.axis)}
            points={compass.points}
            anonymousLabel={L("details.anonymous")}
            ariaLabel={t("compass.details.mapHeading")}
          />
          <!-- Where the room sits on each axis. Not a histogram: the
               coordinates are means of a handful of values, so a bar
               chart of them would be a picture of the question count. -->
          <div class="axis-stats">
            {#each compass.axes as row (row.axis.axis)}
              <div class="axis-stat">
                <p class="axis-stat-name">{row.axis.name}</p>
                {#if row.axis.description}
                  <p class="muted q-meta">{row.axis.description}</p>
                {/if}
                <!-- The bar is the axis, so it runs the full width and
                     both side names sit under its ends: a name beside
                     the track shortens it by however long that word is,
                     and the two axes then draw at different lengths. -->
                <div class="axis-track">
                  <span class="axis-bar">
                    <!-- How sure the mean is, drawn behind it: a room
                         that agrees and a room that is split do not draw
                         the same. -->
                    {#if row.ci_low != null && row.ci_high != null}
                      <span
                        class="axis-spread"
                        style:left={`${((row.ci_low + 1) / 2) * 100}%`}
                        style:width={`${((row.ci_high - row.ci_low) / 2) * 100}%`}
                      ></span>
                    {/if}
                    {#if row.average != null}
                      <span class="axis-marker" style:left={`${((row.average + 1) / 2) * 100}%`}
                      ></span>
                    {/if}
                  </span>
                </div>
                <div class="axis-ends-row muted">
                  <span>{row.axis.low_name}</span>
                  <span class="axis-end-right">{row.axis.high_name}</span>
                </div>
                {#if row.average != null && row.ci_low != null && row.ci_high != null}
                  <p class="muted q-meta">
                    {t("compass.details.interval", {
                      avg: formatDecimal(row.average, locale()),
                      low: formatDecimal(row.ci_low, locale()),
                      high: formatDecimal(row.ci_high, locale()),
                    })}
                  </p>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </AppCard>
    {/if}

    <AppCard>
      <div class="summary-header">
        <h2>{L("details.responsesTitle")}</h2>
        <div class="header-actions">
          <AppButton
            label={L("details.exportCsv")}
            size="small"
            severity="secondary"
            text
            icon="download"
            disabled={!summary || summary.submission_count === 0}
            onclick={exportCsv}
          />
          {#if summary}
            <RecoverLinksPill
              count={summary.submission_count}
              cap={auth.user?.participant_cap ?? null}
              label={L("details.responses")}
              loadRows={recoverRows}
              recoverPath={(id) =>
                `/api/v1/${api.resource}/${formId}/submissions/${id}/edit-link`}
              publicUrl={(tok) => `${publicFormUrl(api.resource, slug)}?s=${tok}`}
            />
          {/if}
        </div>
      </div>

      {#if !summary || summary.submission_count === 0}
        <p class="muted">{L("details.noResponsesYet")}</p>
      {:else}
        <!-- How the room did, above the per-question breakdown that says
             which question it was that did for them. -->
        {#if isQuiz && summary.score_average != null}
          <p class="muted q-meta score-line">
            {t("quiz.details.scoreLine", {
              avg: summary.score_average,
              best: summary.score_best,
              max: summary.max_score,
            })}
          </p>
        {/if}

        {#each summary.questions as q (q.id)}
          <div class="q-block">
            <p class="q-prompt">{q.prompt}</p>
            <!-- The one aggregate a quiz has that a questionnaire cannot:
                 the share who got it right, which is what says a question
                 was broken rather than hard. -->
            {#if q.correct_share != null}
              <p class="muted q-meta">
                {t("quiz.details.correctShare", { pct: Math.round(q.correct_share * 100) })}
              </p>
            {/if}

            {#if q.kind === "rating" && q.rating_distribution}
              {@const dist = q.rating_distribution}
              <p class="muted q-meta">
                {t("form.details.qResponses", { n: q.response_count })}
                {#if q.rating_average}
                  · {t("form.details.qAverage", {
                    avg: formatAverage(q.rating_average, locale()),
                  })}
                {/if}
              </p>
              <!-- The average restated as what it was worth: "3,8 van 5"
                   says how people answered, "0,4 richting Links" says
                   what it did to the map. -->
              {#if isCompass && q.pole && q.rating_average}
                <p class="muted q-meta">
                  {t("compass.details.ratingContribution", {
                    avg: formatAverage(q.rating_average, locale()),
                    value: ratingContribution(q.rating_average, q.pole),
                    pole: poleName(q.pole),
                  })}
                </p>
              {/if}
              <!-- One grid per question, so the label column sizes to the
                   widest entry in this block and every track gets the
                   same remaining width. That is what makes the bars
                   comparable inside a question. -->
              <div class="bars">
                {#each [1, 2, 3, 4, 5] as i (i)}
                  <span class="bar-label">{i}</span>
                  <StatBar segments={[{ width: barWidth(dist, dist[i - 1]) }]} />
                  <span class="bar-count">{dist[i - 1]}</span>
                {/each}
              </div>
            {:else if q.kind === "number"}
              <!-- Four numbers rather than a chart: buckets for an
                   arbitrary range are a choice with no obvious right
                   answer, and "what did people say" for an age or a
                   headcount is answered by these
                   (docs/design-quizzes.md part 2). The raw values are in
                   the CSV. -->
              <p class="muted q-meta">
                {L("details.qResponses", { n: q.response_count })}
                {#if q.number_average != null}
                  · {t("form.details.qAverage", {
                    avg: formatAverage(q.number_average, locale()),
                  })}
                  · {t("form.details.qRange", { low: q.number_min, high: q.number_max })}
                {/if}
              </p>
              <!-- One bar per allowed value while the question's own
                   bounds and step leave few of them, binned past that
                   (``services/numbers``). -->
              {#if q.number_buckets?.length}
                {@const buckets = q.number_buckets}
                <div class="bars">
                  {#each buckets as bucket (bucket.label)}
                    <span class="bar-label">{bucket.label}</span>
                    <StatBar
                      segments={[
                        { width: barWidth(buckets.map((b) => b.count), bucket.count) },
                      ]}
                    />
                    <span class="bar-count">{bucket.count}</span>
                  {/each}
                </div>
              {/if}
            {:else if q.kind === "text" || q.kind === "short_text"}
              {#if !q.texts || q.texts.length === 0}
                <p class="muted q-meta">{L("details.noTextResponses")}</p>
              {:else}
                <ul class="texts">
                  {#each q.texts as txt, i (i)}
                    <li>{txt}</li>
                  {/each}
                </ul>
              {/if}
            {:else if (q.kind === "multiple_choice" || q.kind === "multiple_answer") && q.choice_counts}
              {@const counts = q.choice_counts}
              <p class="muted q-meta">{t("form.details.qResponses", { n: q.response_count })}</p>
              <div class="bars">
                {#each Object.entries(counts) as [label, count] (label)}
                  <span class="bar-label choice-label">
                    <!-- The option's own words, and on a kompas the side
                         it pushed toward, held right so the directions
                         line up down the block. The axis is named once
                         in the overview above. -->
                    <span class="choice-text" title={label}>{label}</span>
                    {#if isCompass}
                      <span class="option-pole">{optionPoleSide(q.id, label)}</span>
                    {/if}
                  </span>
                  <StatBar
                    segments={[{ width: barWidth(Object.values(counts), count) }]}
                  />
                  <span class="bar-count">{count}</span>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      {/if}
    </AppCard>
  {/if}
</DetailsPageShell>

<style>
/* The header is ``DetailHeaderCard`` and owns its own layout; the
 * summary header row comes from theme.css. */

/* The map card's two axis readouts. */
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
 * two axes the same length as each other. The same shape the
 * respondent's own result page uses. */
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
  /* A room that all answered the same has no width to draw, so it still
   * gets a sliver rather than disappearing under the marker. */
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
/* The direction an option or a statement carried, read on the row of
 * the thing it belongs to. */
.option-pole {
  margin-left: 0.5rem;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}

/* What the two axes are, above the questions that place people on
 * them. */
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

/* What was asked: one row per question, the prompt with a small kind
 * label, and the options as pills. */
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
/* The right answer, marked where the options are listed. */
.q-overview-options li.is-key {
  background: var(--brand-green-soft);
  border-color: var(--brand-green);
  color: var(--brand-text);
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
.q-prompt {
  margin: 0 0 0.5rem;
  font-weight: 600;
}
.q-meta {
  margin: 0 0 0.5rem;
}
/* One grid per question block: the label column sizes to the widest
 * entry in this block, and every track gets the same remaining width.
 * That gives the two things the data needs, bars comparable within a
 * question and the tallest one filling the track. */
.bars {
  display: grid;
  grid-template-columns: minmax(1.25rem, max-content) 1fr 2.5rem;
  align-items: center;
  gap: 0.375rem 0.5rem;
  font-size: 0.875rem;
}
.bar-label {
  color: var(--brand-text-muted);
}
.choice-label {
  /* The option left, the side it pushed toward right, so the directions
   * read as a column. A long option is clipped rather than wrapped: a
   * label two lines tall pushes its own bar out of line with the ones
   * above it, and the full text is on the title. */
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
  white-space: pre-line;
}
</style>
