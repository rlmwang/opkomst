<script setup lang="ts">
/**
 * Taking a quiz: a cover, one question at a time, then the score.
 *
 * The cover carries everything about the quiz as a thing: the picture,
 * the title, the description, the privacy disclosure, and the one
 * question that is not part of the quiz, which is who is playing. Then
 * it gets out of the way. A question page is the title and the
 * question, nothing else: a picture and three paragraphs above every
 * question push it under the fold, and the fold is where a quiz loses
 * people.
 *
 * Asking the name here rather than at the end is the same thought. On
 * the result screen it competes with the score and is missed.
 *
 * The walk is the only thing here a questionnaire does not do
 * (``docs/design-quizzes.md`` part 3.1). Everything else is shared:
 * the shell, the top card, the disclosure, and ``QuestionField``,
 * which renders every kind for both products.
 *
 * You can go back and change an answer until you finish, because this
 * is a quiz at a party rather than an exam, and locking each answer
 * would need a round-trip per question for nothing. Grading happens
 * server-side on the one POST at the end; the answer key is not in the
 * page before that.
 */
import { computed, onMounted, ref } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import PublicTopCard from "@/public_shared/PublicTopCard.vue";
import MarkedAnswer from "./MarkedAnswer.vue";
import QuestionField from "@/public_shared/QuestionField.vue";
import SupportButtons from "@/public_shared/SupportButtons.vue";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  ApiError,
  type PublicQuiz,
  type PublicQuizQuestion,
  type QuizResult,
  type SubmitAnswer,
  fetchQuizBySlug,
  fetchQuizResult,
  postQuizAnswers,
} from "./api";
import { quizStrings } from "./i18n";

const slug = window.location.pathname.replace(/^\/q\//, "").split("/")[0];
/** ``?s={token}`` reopens a finished attempt. Read-only: there is no
 *  PUT on a quiz submission. */
const resultToken = new URLSearchParams(window.location.search).get("s");

const quiz = ref<PublicQuiz | null>(null);
const result = ref<QuizResult | null>(null);
/** ``ready`` is the cover; ``playing`` is the walk. */
const status = ref<"loading" | "ready" | "playing" | "unavailable" | "load-failed" | "done">("loading");
const submitting = ref(false);
const stepError = ref<string | null>(null);

const locale = ref<Locale>("nl");
const c = computed(() => chromeStrings(locale.value));
const q = computed(() => quizStrings(locale.value));

const title = computed(() =>
  quiz.value ? resolveText(quiz.value.name_nl, quiz.value.name_en, locale.value) : null,
);
const description = computed(() =>
  quiz.value ? resolveText(quiz.value.description_nl, quiz.value.description_en, locale.value) : null,
);

// Optional pseudonym, real or not: the same contract every public
// surface here has. Asked on the cover, where it is the only thing to
// answer, and sent with the answers.
const displayName = ref("");

/** The scorecard: one cell per scored question, in the order they were
 *  asked. Filled when it was right. It is the answer sheet from a pub
 *  quiz, and it says at a glance which ones went wrong, which a total
 *  cannot. */
const rightCount = computed(() => result.value?.answers.filter((a) => a.correct).length ?? 0);

type Answer = { answer_int?: number | null; answer_text?: string; answer_choices?: string[] };
const answers = ref<Record<string, Answer>>({});
const step = ref(0);

const questions = computed<PublicQuizQuestion[]>(() => quiz.value?.questions ?? []);
const current = computed<PublicQuizQuestion | null>(() => questions.value[step.value] ?? null);
const isLast = computed(() => step.value >= questions.value.length - 1);
const byId = computed(() => Object.fromEntries(questions.value.map((item) => [item.id, item])));

onMounted(async () => {
  const inlined = window.__OPKOMST_QUIZ__;
  if (inlined === null) {
    status.value = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchQuizBySlug(slug));
    quiz.value = loaded;
    locale.value = pickLocale(loaded.locale);
    for (const item of loaded.questions) {
      if (item.kind === "rating" || item.kind === "number") answers.value[item.id] = { answer_int: null };
      else if (item.kind === "text" || item.kind === "short_text") answers.value[item.id] = { answer_text: "" };
      else answers.value[item.id] = { answer_choices: [] };
    }
    if (resultToken) {
      // Came back to a finished attempt: the score, not the questions.
      result.value = await fetchQuizResult(resultToken);
      status.value = "done";
      return;
    }
    status.value = "ready";
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

function isAnswered(item: PublicQuizQuestion): boolean {
  const a = answers.value[item.id] ?? {};
  if (item.kind === "rating" || item.kind === "number") return a.answer_int != null;
  // Ticking nothing on a multiple-choice question is an answer: "none
  // of these" is a position, and it is marked like any other.
  if (item.kind === "multi_choice") return true;
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
  // told at the end which of ten questions was missed is worse than
  // being told here.
  if (item.required && !isAnswered(item)) {
    stepError.value = q.value.answerFirst;
    return;
  }
  stepError.value = null;
  if (!isLast.value) {
    step.value += 1;
    return;
  }
  await finish();
}

async function finish() {
  if (!quiz.value || submitting.value) return;
  submitting.value = true;
  try {
    const payload: SubmitAnswer[] = questions.value.map((item) => {
      const a = answers.value[item.id] ?? {};
      if (item.kind === "rating" || item.kind === "number")
        return { question_id: item.id, answer_int: a.answer_int ?? null };
      if (item.kind === "text" || item.kind === "short_text")
        return { question_id: item.id, answer_text: a.answer_text ?? "" };
      return { question_id: item.id, answer_choices: a.answer_choices ?? [] };
    });
    result.value = await postQuizAnswers(slug, {
      display_name: displayName.value.trim() || null,
      answers: payload,
    });
    // The token in the URL, so a refresh reopens the result instead of
    // starting the quiz again.
    window.history.replaceState(null, "", `/q/${slug}?s=${result.value.edit_token}`);
    status.value = "done";
  } catch {
    stepError.value = c.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

</script>

<template>
  <PublicShell v-model:locale="locale" :hide-ads="status === 'done'">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />

    <template v-else-if="quiz">
      <!-- The cover. Everything about the quiz as a thing, and the one
           question that is not part of it. -->
      <template v-if="status === 'ready'">
        <PublicTopCard
          :title="title"
          :image-url="quiz.image_url"
          :artist="quiz.image_artist_instagram"
          :credit-label="c.imageCredit"
          :description-html="description"
        />
        <Disclosure :locale="locale" />
        <form class="card stack" novalidate @submit.prevent="status = 'playing'">
          <label class="name-label">
            <span class="muted">{{ q.coverName }}</span>
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
            <button type="submit" class="btn-primary">{{ q.start }}</button>
          </div>
        </form>
      </template>

      <!-- A question page carries the title and the question. The
           picture, the description and the disclosure stay on the
           cover, where they were read. -->
      <template v-else-if="status === 'playing'">
        <p class="running-title">{{ title }}</p>
        <div class="card stack">
          <p class="progress muted">{{ q.progress(step + 1, questions.length) }}</p>

          <QuestionField
            v-if="current"
            :key="current.id"
            :question="current"
            :answer="answers[current.id]"
            :required-label="q.required"
            :mark-required="false"
            :range-hint="q.range(current.min_value, current.max_value, current.tolerance, current.step)"
            @update="(value) => (answers[current!.id] = value)"
          />

          <p v-if="stepError" class="error" role="alert">{{ stepError }}</p>

          <div class="step-row">
            <button v-if="step > 0" type="button" class="btn-secondary" @click="back">{{ q.back }}</button>
            <button type="button" class="btn-primary" :disabled="submitting" @click="next">
              {{ isLast ? q.finish : q.next }}
            </button>
          </div>
        </div>
      </template>

      <!-- The result. Everything the page was not allowed to know
           until the answering was over. -->
      <template v-else-if="status === 'done' && result">
        <p class="running-title">{{ title }}</p>
        <div class="card stack result-card">
          <!-- One size for the whole line: the emphasis is weight and
               colour, not three type sizes stacked. -->
          <p class="score">
            <span class="score-got">{{ result.score }}</span>
            <span class="score-rest">/ {{ result.max_score }} {{ q.points }}</span>
          </p>
          <p class="score-line muted">
            {{ q.questionsRight(rightCount, result.answers.length) }}
          </p>

          <!-- The scorecard: one cell per question, in the order they
               were asked, filled when it was right. Only when there is
               no list under it: with the reveal on, the numbered rows
               say the same thing at length. -->
          <ol
            v-if="result.answers.length && !result.reveal_answers"
            class="card-strip"
            :aria-label="q.questionsRight(rightCount, result.answers.length)"
          >
            <li
              v-for="(line, i) in result.answers"
              :key="line.question_id"
              class="cell"
              :class="line.correct ? 'is-right' : 'is-wrong'"
            >
              <span class="visually-hidden">{{ line.correct ? q.correct : q.wrong }}</span>
              <span aria-hidden="true">{{ i + 1 }}</span>
            </li>
          </ol>

          <ol v-if="result.reveal_answers && result.answers.length" class="answer-list">
            <li v-for="(line, i) in result.answers" :key="line.question_id" class="answer-row">
              <span class="row-number" aria-hidden="true">{{ i + 1 }}</span>
              <span class="answer-text">
                <span class="answer-prompt">{{ byId[line.question_id]?.prompt }}</span>
                <MarkedAnswer
                  :question="byId[line.question_id]"
                  :line="line"
                  :strings="q"
                  :reveal="result.reveal_answers"
                />
              </span>
              <span class="verdict" :class="line.correct ? 'is-right' : 'is-wrong'">
                <span class="visually-hidden">{{ line.correct ? q.correct : q.wrong }}</span>
                <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                  <path
                    v-if="line.correct"
                    d="M2.5 8.5l3.5 3.5 7.5-8"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <path
                    v-else
                    d="M3.5 3.5l9 9M12.5 3.5l-9 9"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.2"
                    stroke-linecap="round"
                  />
                </svg>
              </span>
            </li>
          </ol>
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

/* --- the result ---------------------------------------------------
 *
 * One loud thing and everything else quiet. The score is the loud
 * thing: the number you got, the number there was, and the word for
 * what they are, on one baseline. */
.result-card {
  gap: 0.75rem;
}
.score {
  margin: 0;
  display: flex;
  align-items: baseline;
  /* Enough air that the slash belongs to neither number. */
  gap: 0.5rem;
  line-height: 1;
}
.score {
  font-size: 2.25rem;
  letter-spacing: -0.01em;
}
.score-got {
  font-weight: 700;
  color: var(--brand-red);
}
.score-rest {
  font-weight: 400;
  color: var(--brand-text-muted);
}
/* A second fact, not the same one again: points are weighted, so how
 * many questions went right is something the total cannot say. It sits
 * under the score rather than against it, and the list below starts
 * clear of both. */
.score-line {
  margin: 0.5rem 0 0;
  font-size: 0.9375rem;
}

/* The scorecard. One cell per question in the order they were asked,
 * filled when it was right: the answer sheet from a pub quiz, and the
 * key to the numbered list under it. */
.card-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  list-style: none;
  margin: 1rem 0 0;
  padding: 0;
}
.cell {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: 1px solid var(--brand-border);
  font-size: 0.8125rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cell.is-right {
  background: var(--brand-green);
  border-color: var(--brand-green);
  color: #fff;
}
.cell.is-wrong {
  background: transparent;
  color: var(--brand-text-muted);
}

.answer-list {
  list-style: none;
  margin: 1.25rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
/* A rule between rows rather than a gap: the list is a table of what
 * happened, and rules are what keep a long one readable. */
.answer-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--brand-border);
}
.row-number {
  width: 1.5rem;
  height: 1.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  border: 1px solid var(--brand-border);
  font-size: 0.75rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  align-self: start;
}
/* Neutral: the mark on the right says how it went, and a number that
 * also said it would be the same thing twice. */
.answer-text {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}
.answer-prompt {
  line-height: 1.4;
}
.verdict {
  display: inline-flex;
  align-items: center;
  align-self: start;
  padding-top: 0.125rem;
}
.verdict.is-right {
  color: var(--brand-green);
}
.verdict.is-wrong {
  color: var(--brand-red);
}

/* --- the cover and the running head ------------------------------- */
.name-label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.9375rem;
}
/* The quiz's name, kept small once it is playing: it says which quiz
 * this is and gets out of the way of the question. */
.running-title {
  margin: 0 0 0.25rem;
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--brand-text-muted);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 420px) {
  .score-got {
    font-size: 2.75rem;
  }
  .step-row {
    flex-direction: column-reverse;
  }
}
</style>
