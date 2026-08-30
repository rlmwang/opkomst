<script lang="ts">
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
import Disclosure from "@/public_shared/Disclosure.svelte";
import PublicNotice from "@/public_shared/PublicNotice.svelte";
import PublicShell from "@/public_shared/PublicShell.svelte";
import PublicTopCard from "@/public_shared/PublicTopCard.svelte";
import MarkedAnswer from "./MarkedAnswer.svelte";
import QuestionField from "@/public_shared/QuestionField.svelte";
import EditLink from "@/public_shared/EditLink.svelte";
import SupportButtons from "@/public_shared/SupportButtons.svelte";
import { useEditLink } from "@/public_shared/useEditLink.svelte";
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
// The secret link back to this attempt. ``confirmSaved`` records the
// token and routes the URL onto it in one step, the same contract the
// other mini-apps use (``public_shared/useEditLink``).
// Held whole, not spread: ``editUrl`` is a getter, and spreading
// would copy the empty string it has before a submit.
const link = useEditLink("q", () => slug);

let quiz = $state<PublicQuiz | null>(null);
let result = $state<QuizResult | null>(null);
/** ``ready`` is the cover; ``playing`` is the walk. */
let status = $state<"loading" | "ready" | "playing" | "unavailable" | "load-failed" | "done">("loading");
let submitting = $state(false);
let stepError = $state<string | null>(null);
let locale = $state<Locale>("nl");

const c = $derived(chromeStrings(locale));
const q = $derived(quizStrings(locale));

const title = $derived(quiz ? resolveText(quiz.name_nl, quiz.name_en, locale) : null);
const description = $derived(
  quiz ? resolveText(quiz.description_nl, quiz.description_en, locale) : null,
);

// Optional pseudonym, real or not: the same contract every public
// surface here has. Asked on the cover, where it is the only thing to
// answer, and sent with the answers.
let displayName = $state("");

/** The scorecard: one cell per scored question, in the order they were
 *  asked. Filled when it was right. It is the answer sheet from a pub
 *  quiz, and it says at a glance which ones went wrong, which a total
 *  cannot. */
const rightCount = $derived(result?.answers.filter((a) => a.correct).length ?? 0);

type Answer = { answer_int?: number | null; answer_text?: string; answer_choices?: string[] };
let answers = $state<Record<string, Answer>>({});
let step = $state(0);

const questions = $derived<PublicQuizQuestion[]>(quiz?.questions ?? []);
const current = $derived<PublicQuizQuestion | null>(questions[step] ?? null);
const isLast = $derived(step >= questions.length - 1);
const byId = $derived(Object.fromEntries(questions.map((item) => [item.id, item])));

async function load() {
  const inlined = window.__OPKOMST_QUIZ__;
  if (inlined === null) {
    status = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchQuizBySlug(slug));
    quiz = loaded;
    locale = pickLocale(loaded.locale);
    for (const item of loaded.questions) {
      if (item.kind === "rating" || item.kind === "number") answers[item.id] = { answer_int: null };
      else if (item.kind === "text" || item.kind === "short_text") answers[item.id] = { answer_text: "" };
      else answers[item.id] = { answer_choices: [] };
    }
    if (resultToken) {
      // Came back to a finished attempt: the score, not the questions.
      result = await fetchQuizResult(resultToken);
      link.confirmSaved(result.edit_token);
      status = "done";
      return;
    }
    status = "ready";
  } catch (e) {
    status = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
}
void load();

function isAnswered(item: PublicQuizQuestion): boolean {
  const a = answers[item.id] ?? {};
  if (item.kind === "rating" || item.kind === "number") return a.answer_int != null;
  // Ticking nothing on a multiple-choice question is an answer: "none
  // of these" is a position, and it is marked like any other.
  if (item.kind === "multiple_answer") return true;
  return (a.answer_choices ?? []).length > 0;
}

function back() {
  stepError = null;
  if (step > 0) step -= 1;
}

async function next() {
  const item = current;
  if (!item) return;
  // A required question gates the step rather than the submit: being
  // told at the end which of ten questions was missed is worse than
  // being told here.
  if (item.required && !isAnswered(item)) {
    stepError = q.answerFirst;
    return;
  }
  stepError = null;
  if (!isLast) {
    step += 1;
    return;
  }
  await finish();
}

async function finish() {
  if (!quiz || submitting) return;
  submitting = true;
  try {
    const payload: SubmitAnswer[] = questions.map((item) => {
      const a = answers[item.id] ?? {};
      if (item.kind === "rating" || item.kind === "number")
        return { question_id: item.id, answer_int: a.answer_int ?? null };
      if (item.kind === "text" || item.kind === "short_text")
        return { question_id: item.id, answer_text: a.answer_text ?? "" };
      return { question_id: item.id, answer_choices: a.answer_choices ?? [] };
    });
    result = await postQuizAnswers(slug, {
      display_name: displayName.trim() || null,
      answers: payload,
    });
    // The token in the URL, so a refresh reopens the result instead of
    // starting the quiz again.
    link.confirmSaved(result.edit_token);
    status = "done";
  } catch {
    stepError = c.submitFail;
  } finally {
    submitting = false;
  }
}
</script>

<PublicShell bind:locale hideAds={status === "done"}>
  {#if status === "loading"}
    <PublicNotice message={c.loading} />
  {:else if status === "unavailable"}
    <PublicNotice message={c.unavailable} />
  {:else if status === "load-failed"}
    <PublicNotice message={c.loadFailed} />
  {:else if quiz}
    {#if status === "ready"}
      <!-- The cover. Everything about the quiz as a thing, and the one
           question that is not part of it. -->
      <PublicTopCard
        {title}
        imageUrl={quiz.image_url}
        artist={quiz.image_artist_instagram}
        creditLabel={c.imageCredit}
        descriptionHtml={description}
      />
      <Disclosure {locale} />
      <form class="card stack" novalidate onsubmit={(e) => { e.preventDefault(); status = "playing"; }}>
        <label class="name-label">
          <span class="muted">{q.coverName}</span>
          <input
            bind:value={displayName}
            type="text"
            class="input"
            placeholder={c.displayName}
            autocomplete="name"
            maxlength="100"
          />
        </label>
        <div class="step-row">
          <button type="submit" class="btn-primary">{q.start}</button>
        </div>
      </form>
    {:else if status === "playing"}
      <!-- A question page carries the title and the question. The
           picture, the description and the disclosure stay on the
           cover, where they were read. -->
      <p class="running-title">{title}</p>
      <div class="card stack">
        <p class="progress muted">{q.progress(step + 1, questions.length)}</p>

        {#if current}
          {#key current.id}
            <QuestionField
              question={current}
              answer={answers[current.id]}
              requiredLabel={q.required}
              markRequired={false}
              rangeHint={q.range(current.min_value, current.max_value, current.tolerance, current.step)}
              onupdate={(value) => (answers[current!.id] = value)}
            />
          {/key}
        {/if}

        {#if stepError}<p class="error" role="alert">{stepError}</p>{/if}

        <div class="step-row">
          {#if step > 0}
            <button type="button" class="btn-secondary" onclick={back}>{q.back}</button>
          {/if}
          <button type="button" class="btn-primary" disabled={submitting} onclick={next}>
            {isLast ? q.finish : q.next}
          </button>
        </div>
      </div>
    {:else if status === "done" && result}
      <!-- The result. Everything the page was not allowed to know until
           the answering was over. -->
      <p class="running-title">{title}</p>
      <div class="card stack result-card">
        <!-- One size for the whole line: the emphasis is weight and
             colour, not three type sizes stacked. -->
        <!-- No whitespace between the two spans: the second one carries
             its own leading slash, and a newline here would render a
             space the design does not have. -->
        <p class="score"><span class="score-got">{result.score}</span><span
            class="score-rest">/ {result.max_score} {q.points}</span></p>
        <p class="score-line muted">
          {q.questionsRight(rightCount, result.answers.length)}
        </p>

        <!-- The scorecard: one cell per question, in the order they were
             asked, filled when it was right. Only when there is no list
             under it: with the reveal on, the numbered rows say the same
             thing at length. -->
        {#if result.answers.length && !result.reveal_answers}
          <ol class="card-strip" aria-label={q.questionsRight(rightCount, result.answers.length)}>
            {#each result.answers as line, i (line.question_id)}
              <li class="cell" class:is-right={line.correct} class:is-wrong={!line.correct}>
                <span class="visually-hidden">{line.correct ? q.correct : q.wrong}</span>
                <span aria-hidden="true">{i + 1}</span>
              </li>
            {/each}
          </ol>
        {/if}

        {#if result.reveal_answers && result.answers.length}
          <ol class="answer-list">
            {#each result.answers as line, i (line.question_id)}
              <li class="answer-row">
                <span class="row-number" aria-hidden="true">{i + 1}</span>
                <span class="answer-text">
                  <span class="answer-prompt">{byId[line.question_id]?.prompt}</span>
                  <MarkedAnswer
                    question={byId[line.question_id]}
                    {line}
                    strings={q}
                    reveal={result.reveal_answers}
                  />
                </span>
                <span class="verdict" class:is-right={line.correct} class:is-wrong={!line.correct}>
                  <span class="visually-hidden">{line.correct ? q.correct : q.wrong}</span>
                  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                    {#if line.correct}
                      <path
                        d="M2.5 8.5l3.5 3.5 7.5-8"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    {:else}
                      <path
                        d="M3.5 3.5l9 9M12.5 3.5l-9 9"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.2"
                        stroke-linecap="round"
                      />
                    {/if}
                  </svg>
                </span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>

      <!-- The link back to this attempt, said out loud rather than left
           in the address bar: it is the only way back, and nobody can
           re-send it. Same card on every mini-app. -->
      <div class="card link-card">
        <!-- A quiz is never editable: seeing the score and then changing
             the answers is the definition of cheating. -->
        <EditLink url={link.editUrl} {locale} canEdit={false} />
      </div>
      <SupportButtons />
    {/if}
  {/if}
</PublicShell>

<style>
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
/* Matches ``PublicConfirmation``: EditLink renders as a fragment, so
 * the card owns the column and its gap. */
.link-card {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
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
