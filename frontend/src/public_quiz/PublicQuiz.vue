<script setup lang="ts">
/**
 * Taking a quiz: one question at a time, then the score.
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
const status = ref<"loading" | "ready" | "unavailable" | "load-failed" | "done">("loading");
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
// surface here has.
const displayName = ref("");

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
  if (item.kind === "text" || item.kind === "short_text") return (a.answer_text ?? "").trim().length > 0;
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

/** What the right answer was, in words, for the result list. */
function rightAnswer(line: QuizResult["answers"][number]): string | null {
  if (line.correct_text) return line.correct_text;
  if (line.correct_int !== null) return String(line.correct_int);
  if (line.correct_choices?.length) return line.correct_choices.join(", ");
  return null;
}
</script>

<template>
  <PublicShell v-model:locale="locale" :hide-ads="status === 'done'">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />

    <template v-else-if="quiz">
      <PublicTopCard
        :title="title"
        :image-url="quiz.image_url"
        :artist="quiz.image_artist_instagram"
        :credit-label="c.imageCredit"
        :description-html="description"
      />
      <Disclosure :locale="locale" />

      <!-- The result. Everything the page was not allowed to know
           until the answering was over. -->
      <div v-if="status === 'done' && result" class="card stack">
        <h2 class="score-heading">{{ q.scoreHeading }}</h2>
        <p class="score">{{ q.scoreLine(result.score, result.max_score) }}</p>

        <template v-if="result.reveal_answers && result.answers.length">
          <h3 class="answers-heading">{{ q.yourAnswers }}</h3>
          <ul class="answer-list">
            <li v-for="line in result.answers" :key="line.question_id" class="answer-row">
              <span class="mark" :class="line.correct ? 'is-right' : 'is-wrong'">
                {{ line.correct ? q.correct : q.wrong }}
              </span>
              <span class="answer-text">
                <span class="answer-prompt">{{ byId[line.question_id]?.prompt }}</span>
                <span v-if="!line.correct && rightAnswer(line)" class="muted">
                  {{ q.rightAnswer }} {{ rightAnswer(line) }}
                </span>
              </span>
            </li>
          </ul>
        </template>
        <SupportButtons :locale="locale" />
      </div>

      <!-- One question, and the two buttons that move between them. -->
      <div v-else class="card stack">
        <p class="progress muted">{{ q.progress(step + 1, questions.length) }}</p>

        <!-- The pseudonym is asked once, on the first question, so the
             quiz opens with a question rather than with a form. -->
        <input
          v-if="step === 0"
          v-model="displayName"
          type="text"
          class="input"
          :placeholder="c.displayName"
          autocomplete="name"
          maxlength="100"
        />

        <QuestionField
          v-if="current"
          :key="current.id"
          :question="current"
          :answer="answers[current.id]"
          :required-label="q.required"
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
.score-heading {
  margin: 0;
  font-size: 1.125rem;
}
.score {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--brand-red);
}
.answers-heading {
  margin: 0.5rem 0 0;
  font-size: 1rem;
}
.answer-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.answer-row {
  display: flex;
  gap: 0.625rem;
  align-items: baseline;
}
/* A word, not a colour alone: green and red are the same thing to a
 * reader who cannot tell them apart. */
.mark {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.mark.is-right {
  color: var(--brand-green);
}
.mark.is-wrong {
  color: var(--brand-red);
}
.answer-text {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}
.answer-prompt {
  line-height: 1.4;
}
</style>
