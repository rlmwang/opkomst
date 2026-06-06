<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BrandMark from "@/public/BrandMark.vue";
import {
  ApiError,
  type PublicForm,
  type PublicFormQuestion,
  type SubmitAnswer,
  fetchFormBySlug,
  postSubmission,
} from "./api";
import { type Locale, pickLocale, strings } from "./i18n";

// --- Slug + locale -----------------------------------------------

// Slug is parsed from the URL directly. Same shape as the events
// mini-app: ``/f/<slug>``; segments after the slug are ignored.
const slug = window.location.pathname.replace(/^\/f\//, "").split("/")[0];

// Per-form state. Inline payload wins when the backend put it on
// the window; the dev path (Vite serving the static HTML without
// the backend in front) falls back to a fetch.
const form = ref<PublicForm | null>(null);
const status = ref<"loading" | "ready" | "unavailable" | "load-failed" | "submitted">(
  "loading",
);
const submitting = ref(false);

const locale = ref<Locale>("nl");
const s = computed(() => strings(locale.value));

onMounted(async () => {
  const inlined = window.__OPKOMST_FORM__;
  if (inlined === null) {
    // Backend rendered ``null`` — form unknown or archived.
    status.value = "unavailable";
    return;
  }
  if (inlined !== undefined) {
    form.value = inlined;
    locale.value = pickLocale(inlined.locale);
    document.documentElement.lang = locale.value;
    status.value = "ready";
    initAnswers(inlined);
    return;
  }
  // Dev fallback — fetch the form ourselves.
  try {
    const fetched = await fetchFormBySlug(slug);
    form.value = fetched;
    locale.value = pickLocale(fetched.locale);
    document.documentElement.lang = locale.value;
    status.value = "ready";
    initAnswers(fetched);
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

// --- Answer state ------------------------------------------------

// Keyed by question id. Each answer carries one of three shapes
// depending on kind; the others are absent. The state map is
// rebuilt whenever a fresh form payload arrives so stale keys
// from a since-edited question set can't survive.
type Answer = {
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
};
const answers = ref<Record<string, Answer>>({});

function initAnswers(f: PublicForm): void {
  const next: Record<string, Answer> = {};
  for (const q of f.questions) {
    if (q.kind === "rating") next[q.id] = { answer_int: null };
    else if (q.kind === "text" || q.kind === "short_text") next[q.id] = { answer_text: "" };
    else next[q.id] = { answer_choices: [] };
  }
  answers.value = next;
}

function setRating(qid: string, value: number) {
  answers.value[qid] = { answer_int: value };
}
function setText(qid: string, value: string) {
  answers.value[qid] = { answer_text: value };
}
function setSingle(qid: string, value: string) {
  answers.value[qid] = { answer_choices: value ? [value] : [] };
}
function toggleMulti(qid: string, option: string, checked: boolean) {
  const current = answers.value[qid].answer_choices ?? [];
  answers.value[qid] = {
    answer_choices: checked
      ? [...current.filter((c) => c !== option), option]
      : current.filter((c) => c !== option),
  };
}
function isChecked(qid: string, option: string): boolean {
  return (answers.value[qid].answer_choices ?? []).includes(option);
}

function isAnswered(q: PublicFormQuestion): boolean {
  const a = answers.value[q.id] ?? {};
  if (q.kind === "rating") return a.answer_int != null;
  if (q.kind === "text" || q.kind === "short_text")
    return (a.answer_text ?? "").trim().length > 0;
  return (a.answer_choices ?? []).length > 0;
}

// --- Submit ------------------------------------------------------

const submitError = ref<string | null>(null);

async function submit() {
  if (!form.value) return;
  // Client-side required-question check mirrors the backend.
  for (const q of form.value.questions) {
    if (q.required && !isAnswered(q)) {
      submitError.value = `${s.value.missingRequiredPrefix} ${q.prompt}`;
      return;
    }
  }
  submitError.value = null;
  submitting.value = true;

  // Build the wire payload. Drop kind-incompatible fields per
  // answer so the request body stays tight.
  const payload: SubmitAnswer[] = form.value.questions.map((q) => {
    const a = answers.value[q.id] ?? {};
    if (q.kind === "rating") return { question_id: q.id, answer_int: a.answer_int ?? null };
    if (q.kind === "text" || q.kind === "short_text")
      return { question_id: q.id, answer_text: a.answer_text ?? "" };
    return { question_id: q.id, answer_choices: a.answer_choices ?? [] };
  });

  try {
    await postSubmission(slug, { answers: payload });
    status.value = "submitted";
  } catch (e) {
    submitError.value =
      e instanceof ApiError && e.status === 410 ? s.value.unavailable : s.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

const ratings = computed(() => [1, 2, 3, 4, 5]);
</script>

<template>
  <div class="page">
    <header class="public-header">
      <BrandMark />
    </header>

    <main class="container stack">
      <div v-if="status === 'loading'" class="card stack">
        <p class="muted">{{ s.loading }}</p>
      </div>

      <div v-else-if="status === 'unavailable'" class="card stack">
        <p>{{ s.unavailable }}</p>
      </div>

      <div v-else-if="status === 'load-failed'" class="card stack">
        <p>{{ s.loadFailed }}</p>
      </div>

      <div v-else-if="status === 'submitted'" class="card stack">
        <h2>{{ s.thanks }}</h2>
        <p class="muted">{{ s.thanksBody }}</p>
      </div>

      <template v-else-if="form">
        <div class="card stack">
          <h1>{{ form.name }}</h1>
        </div>

        <form class="stack" novalidate @submit.prevent="submit">
          <div v-for="q in form.questions" :key="q.id" class="card stack q-card">
            <label class="prompt">
              {{ q.prompt }}
              <span v-if="q.required" class="required-mark" :aria-label="s.required">*</span>
            </label>

            <!-- rating -->
            <div v-if="q.kind === 'rating'" class="rating">
              <div class="rating-row">
                <button
                  v-for="v in ratings"
                  :key="v"
                  type="button"
                  class="dot"
                  :class="{ active: answers[q.id]?.answer_int === v }"
                  :aria-label="String(v)"
                  @click="setRating(q.id, v)"
                >{{ v }}</button>
              </div>
              <div v-if="q.low_label || q.high_label" class="legend">
                <span>{{ q.low_label ?? '' }}</span>
                <span>{{ q.high_label ?? '' }}</span>
              </div>
            </div>

            <!-- long text -->
            <textarea
              v-else-if="q.kind === 'text'"
              :value="answers[q.id]?.answer_text ?? ''"
              maxlength="2000"
              rows="3"
              class="textfield textarea"
              @input="(e) => setText(q.id, (e.target as HTMLTextAreaElement).value)"
            />

            <!-- short text -->
            <input
              v-else-if="q.kind === 'short_text'"
              type="text"
              :value="answers[q.id]?.answer_text ?? ''"
              maxlength="200"
              class="textfield"
              @input="(e) => setText(q.id, (e.target as HTMLInputElement).value)"
            />

            <!-- single choice -->
            <div v-else-if="q.kind === 'single_choice'" class="choice-list">
              <label v-for="opt in q.options" :key="opt" class="choice-row">
                <input
                  type="radio"
                  :name="`q-${q.id}`"
                  :value="opt"
                  :checked="(answers[q.id]?.answer_choices ?? [])[0] === opt"
                  @change="setSingle(q.id, opt)"
                />
                <span>{{ opt }}</span>
              </label>
            </div>

            <!-- multi choice -->
            <div v-else-if="q.kind === 'multi_choice'" class="choice-list">
              <label v-for="opt in q.options" :key="opt" class="choice-row">
                <input
                  type="checkbox"
                  :checked="isChecked(q.id, opt)"
                  @change="(e) => toggleMulti(q.id, opt, (e.target as HTMLInputElement).checked)"
                />
                <span>{{ opt }}</span>
              </label>
            </div>
          </div>

          <div v-if="submitError" class="card error">
            <p>{{ submitError }}</p>
          </div>

          <div class="submit-row">
            <button type="submit" class="primary" :disabled="submitting">
              {{ submitting ? s.submitting : s.submit }}
            </button>
          </div>
        </form>
      </template>
    </main>
  </div>
</template>

<style scoped>
/* Layout chrome — copied from the public-event mini-app pattern.
 * No PrimeVue, no theme.css overrides beyond the shared brand
 * variables (those come in via the global ``theme.css`` import
 * in ``main.ts``). */
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.public-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
}
.container {
  width: 100%;
  max-width: 640px;
  margin: 0 auto;
  padding: 0 1.25rem 2rem;
}
.stack > * + * {
  margin-top: 0.75rem;
}
.card {
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 12px;
  padding: 1rem 1.25rem;
}
.q-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.muted {
  color: var(--brand-text-muted);
  margin: 0;
}
.error {
  border-color: #f5b0b4;
  background: #fbdadc;
}
.prompt {
  font-weight: 600;
  font-size: 1.0625rem;
  line-height: 1.4;
}
.required-mark {
  color: var(--brand-red);
  margin-left: 0.125rem;
}

/* --- Rating --------------------------------------------------- */
.rating {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.rating-row {
  display: flex;
  gap: 0.5rem;
}
.dot {
  flex: 1;
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
  font-size: 1rem;
  font-weight: 600;
  padding: 0.625rem 0;
  border-radius: 8px;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.dot:hover {
  border-color: var(--brand-red);
}
.dot.active {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #fff;
}
.legend {
  display: flex;
  justify-content: space-between;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}

/* --- Text inputs ---------------------------------------------- */
.textfield {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.4;
}
.textfield:focus {
  outline: 2px solid var(--brand-red);
  outline-offset: 0;
  border-color: var(--brand-red);
}
.textarea {
  resize: vertical;
  min-height: 5rem;
}

/* --- Choice lists --------------------------------------------- */
.choice-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.choice-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}
.choice-row input {
  width: 1.125rem;
  height: 1.125rem;
}

/* --- Submit --------------------------------------------------- */
.submit-row {
  display: flex;
  justify-content: flex-end;
}
.primary {
  background: var(--brand-red);
  color: #fff;
  border: 1px solid var(--brand-red);
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
}
.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
