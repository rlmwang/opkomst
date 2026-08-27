<script setup lang="ts">
/**
 * Filling in a kompas: a cover, one question at a time, then the map.
 *
 * The cover carries everything about the kompas as a thing (picture,
 * title, description, disclosure) and the one question that is not part
 * of it, which is who is filling it in. That question needs a sentence
 * the other five products do not: the name is going on a chart everyone
 * else will read, and the moment to say so is above the box rather than
 * after the submit (``docs/design-kompas.md`` 5.1).
 *
 * A question page is the title and the question, nothing else. The
 * directions are not in this page: which answer moves you where arrives
 * with the result, the same seam and the same reason as the quiz's
 * answer key.
 *
 * The result is three blocks, in this order: the map, because it is
 * what the person came for; where they landed on each axis, in the
 * organiser's own words; and every question redrawn as it was asked
 * with the direction it carried, so the map has a visible reason.
 *
 * Unlike a quiz, the answers stay editable. Changing your answer after
 * seeing the map is changing your mind, not a second attempt.
 */
import { computed, onMounted, ref } from "vue";
import CompassPlot from "@/public_shared/CompassPlot.vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import PublicTopCard from "@/public_shared/PublicTopCard.vue";
import QuestionField from "@/public_shared/QuestionField.vue";
import RecoveredNotice from "@/public_shared/RecoveredNotice.vue";
import SupportButtons from "@/public_shared/SupportButtons.vue";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  ApiError,
  type CompassAnswerResult,
  type CompassAxis,
  type CompassResult,
  type Pole,
  type PublicCompass,
  type PublicCompassQuestion,
  type SubmitAnswer,
  fetchCompassBySlug,
  fetchCompassResult,
  postCompassAnswers,
  putCompassAnswers,
} from "./api";
import { compassStrings, decimal } from "./i18n";

const slug = window.location.pathname.replace(/^\/k\//, "").split("/")[0];
/** ``?s={token}`` reopens a finished fill-in: the map, and the answers
 *  behind the "change your answers" button. */
const resultToken = new URLSearchParams(window.location.search).get("s");

const kompas = ref<PublicCompass | null>(null);
const result = ref<CompassResult | null>(null);
/** ``ready`` is the cover; ``walking`` is the questions. */
const status = ref<"loading" | "ready" | "walking" | "unavailable" | "load-failed" | "done">("loading");
const submitting = ref(false);
const stepError = ref<string | null>(null);
/** Set once a token is in hand: the next save is a PUT rather than a
 *  POST, whether it came from the URL or from the first submit. */
const token = ref<string | null>(resultToken);

const locale = ref<Locale>("nl");
const c = computed(() => chromeStrings(locale.value));
const k = computed(() => compassStrings(locale.value));

const title = computed(() =>
  kompas.value ? resolveText(kompas.value.name_nl, kompas.value.name_en, locale.value) : null,
);
const description = computed(() =>
  kompas.value ? resolveText(kompas.value.description_nl, kompas.value.description_en, locale.value) : null,
);

const displayName = ref("");

type Answer = { answer_int?: number | null; answer_text?: string; answer_choices?: string[] };
const answers = ref<Record<string, Answer>>({});
const step = ref(0);

const questions = computed<PublicCompassQuestion[]>(() => kompas.value?.questions ?? []);
const current = computed<PublicCompassQuestion | null>(() => questions.value[step.value] ?? null);
const isLast = computed(() => step.value >= questions.value.length - 1);
const byId = computed(() => Object.fromEntries(questions.value.map((item) => [item.id, item])));

/** The axes, in the order the plot draws them. Taken from the result
 *  when there is one, because that is the copy the map was built from,
 *  and from the cover payload before that. */
const axes = computed<CompassAxis[]>(() => result.value?.axes ?? kompas.value?.axes ?? []);

function blankAnswers(loaded: PublicCompass): void {
  for (const item of loaded.questions) {
    if (item.kind === "rating" || item.kind === "number") answers.value[item.id] = { answer_int: null };
    else if (item.kind === "text" || item.kind === "short_text") answers.value[item.id] = { answer_text: "" };
    else answers.value[item.id] = { answer_choices: [] };
  }
}

/** Refill the walk from a result. The per-answer rows carry what was
 *  given, so reopening a link and pressing "change your answers" starts
 *  from the answers rather than from an empty form. */
function fillFrom(found: CompassResult): void {
  for (const line of found.answers) {
    if (line.given_int != null) answers.value[line.question_id] = { answer_int: line.given_int };
    else if (line.given_choices) answers.value[line.question_id] = { answer_choices: [...line.given_choices] };
  }
  displayName.value = found.display_name ?? "";
}

onMounted(async () => {
  const inlined = window.__OPKOMST_COMPASS__;
  if (inlined === null) {
    status.value = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchCompassBySlug(slug));
    kompas.value = loaded;
    locale.value = pickLocale(loaded.locale);
    blankAnswers(loaded);
    if (resultToken) {
      const found = await fetchCompassResult(resultToken);
      result.value = found;
      fillFrom(found);
      status.value = "done";
      return;
    }
    status.value = "ready";
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

function isAnswered(item: PublicCompassQuestion): boolean {
  const a = answers.value[item.id] ?? {};
  if (item.kind === "rating") return a.answer_int != null;
  return (a.answer_choices ?? []).length > 0;
}

function back() {
  stepError.value = null;
  if (step.value > 0) step.value -= 1;
}

async function next() {
  const item = current.value;
  if (!item) return;
  // A required question gates the step rather than the submit: being
  // told at the end which of ten was missed is worse than being told
  // here. A skippable one contributes nothing and costs nothing, which
  // is what "no opinion" means on a kompas.
  if (item.required && !isAnswered(item)) {
    stepError.value = k.value.answerFirst;
    return;
  }
  stepError.value = null;
  if (!isLast.value) {
    step.value += 1;
    return;
  }
  await finish();
}

function payload(): SubmitAnswer[] {
  return questions.value.map((item) => {
    const a = answers.value[item.id] ?? {};
    if (item.kind === "rating") return { question_id: item.id, answer_int: a.answer_int ?? null };
    return { question_id: item.id, answer_choices: a.answer_choices ?? [] };
  });
}

async function finish() {
  if (!kompas.value || submitting.value) return;
  submitting.value = true;
  try {
    const body = { display_name: displayName.value.trim() || null, answers: payload() };
    const found = token.value
      ? await putCompassAnswers(token.value, body)
      : await postCompassAnswers(slug, body);
    result.value = found;
    token.value = found.edit_token;
    // The token in the URL, so a refresh reopens the map instead of
    // starting the kompas again.
    window.history.replaceState(null, "", `/k/${slug}?s=${found.edit_token}`);
    status.value = "done";
    step.value = 0;
  } catch {
    stepError.value = c.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

// --- reading the result ----------------------------------------------

/** Where the reader landed on one axis, and how many answers said so. */
function place(axis: CompassAxis): { value: number; counted: number } {
  const found = result.value;
  if (!found) return { value: 0, counted: 0 };
  return axis.axis === "x"
    ? { value: found.x, counted: found.counted_x }
    : { value: found.y, counted: found.counted_y };
}

/** The sentence for one axis. A dot on the centre line has two
 *  possible reasons, and this is where the screen says which. */
function axisSentence(axis: CompassAxis): string {
  const { value, counted } = place(axis);
  if (counted === 0) return k.value.youSaidNothing;
  if (value === 0) return k.value.youAreCentre;
  return k.value.youAreAt(value < 0 ? axis.low_name : axis.high_name);
}

/** The marker's position along a [-1, 1] bar, as a percentage. */
function markerLeft(axis: CompassAxis): string {
  return `${((place(axis).value + 1) / 2) * 100}%`;
}

/** One side of one axis, in the organiser's own words. */
function poleName(pole: Pole | null): string {
  if (!pole) return "";
  const [name, side] = pole.split("_");
  const axis = axes.value.find((a) => a.axis === name);
  if (!axis) return "";
  return side === "low" ? axis.low_name : axis.high_name;
}

/** The direction each option of a choice question carried, by the
 *  option's own place in the list: the two arrive parallel. */
function optionPole(line: CompassAnswerResult, index: number): string {
  return poleName(line.option_poles?.[index] ?? null);
}

function isPicked(line: CompassAnswerResult, option: string): boolean {
  return (line.given_choices ?? []).includes(option);
}

/** What one rating answer did to the map, in words: the side a 5 meant,
 *  what was said, and where that landed. */
function ratingSentence(line: CompassAnswerResult): string {
  const meant = poleName(line.pole);
  const given = line.given_int ?? 0;
  if (!line.value) return k.value.ratingLineCentre(meant, given);
  const toward = line.value < 0 ? poleName(sideOf(line, "low")) : poleName(sideOf(line, "high"));
  return k.value.ratingLine(meant, given, decimal(line.value, locale.value), toward);
}

/** The named side of this answer's own axis, whichever way it went. */
function sideOf(line: CompassAnswerResult, side: "low" | "high"): Pole | null {
  return line.axis ? (`${line.axis}_${side}` as Pole) : null;
}

function startWalk() {
  step.value = 0;
  stepError.value = null;
  status.value = "walking";
}
</script>

<template>
  <PublicShell v-model:locale="locale" :hide-ads="status === 'done'">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />

    <template v-else-if="kompas">
      <!-- The cover. -->
      <template v-if="status === 'ready'">
        <PublicTopCard
          :title="title"
          :image-url="kompas.image_url"
          :artist="kompas.image_artist_instagram"
          :credit-label="c.imageCredit"
          :description-html="description"
        />
        <!-- What the kompas places people on, said before anybody
             answers. The directions per answer are not here. -->
        <ul v-if="axes.length" class="card axis-intro">
          <li v-for="axis in axes" :key="axis.axis">
            <strong class="axis-intro-name">{{ axis.name }}</strong>
            <span v-if="axis.description" class="muted">{{ axis.description }}</span>
            <span class="muted axis-ends">{{ axis.low_name }} &middot; {{ axis.high_name }}</span>
          </li>
        </ul>
        <Disclosure :locale="locale" />
        <form class="card stack" novalidate @submit.prevent="startWalk">
          <label class="name-label">
            <!-- The privacy contract of this feature, above the box and
                 not under it. -->
            <span class="muted">{{ k.nameOnMap }}</span>
            <input
              v-model="displayName"
              type="text"
              class="input"
              :placeholder="c.displayName"
              autocomplete="name"
              maxlength="100"
            />
          </label>
          <div class="step-row">
            <button type="submit" class="btn-primary">{{ k.start }}</button>
          </div>
        </form>
      </template>

      <!-- A question page carries the title and the question. -->
      <template v-else-if="status === 'walking'">
        <p class="running-title">{{ title }}</p>
        <div class="card stack">
          <p class="progress muted">{{ k.progress(step + 1, questions.length) }}</p>

          <QuestionField
            v-if="current"
            :key="current.id"
            :question="current"
            :answer="answers[current.id]"
            :required-label="k.required"
            :mark-required="false"
            :range-hint="null"
            @update="(value) => (answers[current!.id] = value)"
          />

          <p v-if="stepError" class="error" role="alert">{{ stepError }}</p>

          <div class="step-row">
            <button v-if="step > 0" type="button" class="btn-secondary" @click="back">{{ k.back }}</button>
            <button type="button" class="btn-primary" :disabled="submitting" @click="next">
              {{ isLast ? k.finish : k.next }}
            </button>
          </div>
        </div>
      </template>

      <!-- The result: the map, the axes, the answers. -->
      <template v-else-if="status === 'done' && result">
        <p class="running-title">{{ title }}</p>

        <div class="card stack">
          <h2 class="result-heading">{{ k.resultTitle }}</h2>
          <CompassPlot
            :axes="axes"
            :points="result.points" :anonymous-label="k.anonymous"
            :aria-label="k.resultTitle"
          />
          <p class="muted filled-in">{{ k.filledIn(result.points.length) }}</p>
        </div>

        <div class="card stack">
          <div v-for="axis in axes" :key="axis.axis" class="axis-block">
            <p class="axis-name">
              {{ axis.name }}
              <span v-if="axis.description" class="muted axis-desc">{{ axis.description }}</span>
            </p>
            <p class="axis-sentence">{{ axisSentence(axis) }}</p>
            <div class="axis-track">
              <span class="axis-bar">
                <span class="axis-marker" :style="{ left: markerLeft(axis) }" />
              </span>
            </div>
            <div class="axis-ends-row muted">
              <span>{{ axis.low_name }}</span>
              <span class="axis-end-right">{{ axis.high_name }}</span>
            </div>
          </div>
        </div>

        <!-- Every question redrawn as it was asked, with the direction
             it carried: the map gets a visible reason, question by
             question. -->
        <div class="card stack">
          <h2 class="result-heading">{{ k.answersHeading }}</h2>
          <ol class="answer-list">
            <li v-for="(line, i) in result.answers" :key="line.question_id" class="answer-row">
              <span class="row-number" aria-hidden="true">{{ i + 1 }}</span>
              <span class="answer-text">
                <span class="answer-prompt">{{ byId[line.question_id]?.prompt }}</span>

                <!-- A rating is the scale it was: seeing where the pick
                     sat on it is the whole answer. -->
                <template v-if="line.kind === 'rating'">
                  <span class="scale-row" aria-hidden="true">
                    <span
                      v-for="n in 5"
                      :key="n"
                      class="scale-dot"
                      :class="{ 'is-picked': line.given_int === n }"
                      >{{ n }}</span
                    >
                  </span>
                  <span class="answer-note muted">
                    {{ line.given_int == null ? k.noAnswer : ratingSentence(line) }}
                  </span>
                </template>

                <!-- A choice is its option list in the organiser's
                     order, the pick marked in place and each option's
                     direction named beside it. -->
                <template v-else>
                  <span class="option-list">
                    <span
                      v-for="(option, index) in byId[line.question_id]?.options ?? []"
                      :key="option"
                      class="option-row"
                      :class="{ 'is-picked': isPicked(line, option) }"
                    >
                      <span class="option-mark" aria-hidden="true" />
                      <span class="option-name">{{ option }}</span>
                      <span class="option-pole muted">{{ optionPole(line, index) }}</span>
                    </span>
                  </span>
                  <span v-if="!(line.given_choices ?? []).length" class="answer-note muted">{{ k.noAnswer }}</span>
                </template>
              </span>
            </li>
          </ol>

          <RecoveredNotice :recovered-at="result.link_recovered_at" :locale="locale" />
          <div class="step-row">
            <button type="button" class="btn-secondary" @click="startWalk">{{ k.changeAnswers }}</button>
          </div>
        </div>

        <SupportButtons :locale="locale" />
      </template>
    </template>
  </PublicShell>
</template>

<style scoped>
.progress {
  margin: 0;
  font-size: 0.875rem;
}
.step-row {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.error {
  color: var(--brand-red);
  margin: 0;
}
.result-heading {
  margin: 0;
  font-size: 1.125rem;
}
.filled-in {
  margin: 0;
  font-size: 0.875rem;
}

/* The cover's two-line summary of what this places people on. */
.axis-intro {
  list-style: none;
  margin: 0;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.axis-ends {
  display: block;
  font-size: 0.875rem;
}
/* A template's leading space collapses, so the gap is drawn. */
.axis-intro-name {
  margin-right: 0.3125rem;
}

/* --- where you landed, per axis ----------------------------------- */
.axis-block + .axis-block {
  margin-top: 1.25rem;
}
.axis-name {
  margin: 0;
  font-weight: 600;
}
.axis-desc {
  font-weight: 400;
  margin-left: 0.375rem;
}
.axis-sentence {
  margin: 0.25rem 0 0.5rem;
}
.axis-track {
  display: flex;
  align-items: center;
}
.axis-bar {
  position: relative;
  flex: 1 1 auto;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--brand-border);
}
.axis-marker {
  position: absolute;
  top: -0.1875rem;
  width: 0.3125rem;
  height: 0.875rem;
  margin-left: -0.15625rem;
  border-radius: 2px;
  background: var(--brand-red);
}
.axis-ends-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.375rem;
  font-size: 0.875rem;
}
.axis-end-right {
  text-align: right;
}

/* --- your answers -------------------------------------------------
 * The row grammar (.answer-list, .answer-row, .row-number,
 * .answer-prompt) is the quiz result screen's, in
 * ``public_shared/forms.css``. What is different is the direction
 * beside each option, and the absence of any mark that claims an
 * answer was right: a kompas has no right answers. */
.answer-note {
  display: block;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}
.scale-row {
  display: flex;
  gap: 0.375rem;
  margin-top: 0.375rem;
}
.scale-dot {
  width: 1.75rem;
  height: 1.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  font-size: 0.875rem;
}
.scale-dot.is-picked {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #fff;
  font-weight: 600;
}
.option-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.375rem;
}
.option-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.option-mark {
  flex: 0 0 auto;
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--brand-border);
}
.option-row.is-picked .option-mark {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
.option-row.is-picked .option-name {
  font-weight: 600;
}
.option-name {
  flex: 1 1 auto;
  min-width: 0;
}
.option-pole {
  flex: 0 0 auto;
  font-size: 0.875rem;
}
</style>
