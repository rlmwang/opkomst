<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import PublicHero from "@/public_shared/PublicHero.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  ApiError,
  type PublicForm,
  type PublicFormQuestion,
  type SubmitAnswer,
  fetchFormBySlug,
  postSubmission,
} from "./api";
import { formStrings } from "./i18n";

const slug = window.location.pathname.replace(/^\/f\//, "").split("/")[0];

const form = ref<PublicForm | null>(null);
const status = ref<"loading" | "ready" | "unavailable" | "load-failed" | "submitted">("loading");
const submitting = ref(false);

const locale = ref<Locale>("nl");
const c = computed(() => chromeStrings(locale.value));
const f = computed(() => formStrings(locale.value));

// Optional pseudonym (real or not) — same contract as the events
// sign-up name. Empty → anonymous.
const displayName = ref("");

onMounted(async () => {
  const inlined = window.__OPKOMST_FORM__;
  if (inlined === null) {
    status.value = "unavailable";
    return;
  }
  if (inlined !== undefined) {
    form.value = inlined;
    locale.value = pickLocale(inlined.locale);
    status.value = "ready";
    initAnswers(inlined);
    return;
  }
  try {
    const fetched = await fetchFormBySlug(slug);
    form.value = fetched;
    locale.value = pickLocale(fetched.locale);
    status.value = "ready";
    initAnswers(fetched);
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

// --- Answer state ------------------------------------------------

type Answer = {
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
};
const answers = ref<Record<string, Answer>>({});

function initAnswers(form_: PublicForm): void {
  const next: Record<string, Answer> = {};
  for (const q of form_.questions) {
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
  if (q.kind === "text" || q.kind === "short_text") return (a.answer_text ?? "").trim().length > 0;
  return (a.answer_choices ?? []).length > 0;
}

// --- Submit ------------------------------------------------------

const submitError = ref<string | null>(null);

async function submit() {
  if (!form.value) return;
  for (const q of form.value.questions) {
    if (q.required && !isAnswered(q)) {
      submitError.value = `${f.value.missingRequiredPrefix} ${q.prompt}`;
      return;
    }
  }
  submitError.value = null;
  submitting.value = true;

  const payload: SubmitAnswer[] = form.value.questions.map((q) => {
    const a = answers.value[q.id] ?? {};
    if (q.kind === "rating") return { question_id: q.id, answer_int: a.answer_int ?? null };
    if (q.kind === "text" || q.kind === "short_text")
      return { question_id: q.id, answer_text: a.answer_text ?? "" };
    return { question_id: q.id, answer_choices: a.answer_choices ?? [] };
  });

  try {
    await postSubmission(slug, { display_name: displayName.value.trim() || null, answers: payload });
    status.value = "submitted";
  } catch (e) {
    submitError.value = e instanceof ApiError && e.status === 410 ? c.value.unavailable : c.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

const ratings = computed(() => [1, 2, 3, 4, 5]);
</script>

<template>
  <PublicShell v-model:locale="locale">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />
    <PublicNotice v-else-if="status === 'submitted'" :title="c.thanks" :message="f.thanksBody" />

    <template v-else-if="form">
      <div class="card title-card">
        <PublicHero
          :image-url="form.image_url"
          :artist="form.image_artist_instagram"
          :credit-label="c.imageCredit"
        />
        <h1>{{ form.name }}</h1>
        <p v-if="form.description" class="muted">{{ form.description }}</p>
      </div>

      <Disclosure :locale="locale" />

      <form class="card stack form-card" novalidate @submit.prevent="submit">
        <!-- Pseudonym first, mirroring the events sign-up form. -->
        <input
          v-model="displayName"
          type="text"
          class="textfield"
          :placeholder="c.displayName"
          autocomplete="name"
          maxlength="100"
        />

        <div v-for="q in form.questions" :key="q.id" class="q-block">
          <label class="prompt">
            {{ q.prompt }}
            <span v-if="q.required" class="required-mark" :aria-label="f.required">*</span>
          </label>

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

          <textarea
            v-else-if="q.kind === 'text'"
            :value="answers[q.id]?.answer_text ?? ''"
            maxlength="2000"
            rows="3"
            class="textfield textarea"
            @input="(e) => setText(q.id, (e.target as HTMLTextAreaElement).value)"
          />

          <input
            v-else-if="q.kind === 'short_text'"
            type="text"
            :value="answers[q.id]?.answer_text ?? ''"
            maxlength="200"
            class="textfield"
            @input="(e) => setText(q.id, (e.target as HTMLInputElement).value)"
          />

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

        <p v-if="submitError" class="error" role="alert">{{ submitError }}</p>

        <div class="submit-row">
          <button type="submit" class="btn-primary" :disabled="submitting">
            {{ submitting ? c.submitting : c.submit }}
          </button>
        </div>
      </form>
    </template>
  </PublicShell>
</template>

<style scoped>
.muted { color: var(--brand-text-muted); margin: 0.5rem 0 0; }
.title-card h1 { margin: 0; overflow-wrap: anywhere; }
.form-card { display: flex; flex-direction: column; gap: 1.25rem; }
.q-block { display: flex; flex-direction: column; gap: 0.5rem; }
.prompt { font-weight: 600; font-size: 1.0625rem; line-height: 1.4; }
.required-mark { color: var(--brand-red); margin-left: 0.125rem; }
.error { color: var(--brand-red); margin: 0; }

/* --- Rating --- */
.rating { display: flex; flex-direction: column; gap: 0.375rem; }
.rating-row { display: flex; gap: 0.5rem; }
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
.dot:hover { border-color: var(--brand-red); }
.dot.active { background: var(--brand-red); border-color: var(--brand-red); color: #fff; }
.legend { display: flex; justify-content: space-between; font-size: 0.8125rem; color: var(--brand-text-muted); }

/* --- Text inputs --- */
.textfield {
  width: 100%;
  box-sizing: border-box;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.4;
}
.textfield:focus { outline: 2px solid var(--brand-red); outline-offset: 0; border-color: var(--brand-red); }
.textarea { resize: vertical; min-height: 5rem; }

/* --- Choice lists --- */
.choice-list { display: flex; flex-direction: column; gap: 0.375rem; }
.choice-row { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }
.choice-row input { width: 1.125rem; height: 1.125rem; }

/* --- Submit --- */
.submit-row { display: flex; justify-content: flex-end; }
.btn-primary {
  background: var(--brand-red);
  color: #fff;
  border: 1px solid var(--brand-red);
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
