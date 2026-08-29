<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import SupportButtons from "@/public_shared/SupportButtons.vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import QuestionField from "@/public_shared/QuestionField.vue";
import PublicConfirmation from "@/public_shared/PublicConfirmation.vue";
import PublicEditBar from "@/public_shared/PublicEditBar.vue";
import RecoveredNotice from "@/public_shared/RecoveredNotice.vue";
import PublicTopCard from "@/public_shared/PublicTopCard.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { showToast } from "@/lib/toast";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import { useEditForm } from "@/public_shared/useEditForm";
import { useEditLink } from "@/public_shared/useEditLink";
import {
  ApiError,
  type PublicForm,
  type PublicFormQuestion,
  type SubmitAnswer,
  fetchFormBySlug,
  fetchSubmission,
  postSubmission,
  putSubmission,
  withdrawSubmission,
} from "./api";
import { formStrings } from "./i18n";

const slug = window.location.pathname.replace(/^\/f\//, "").split("/")[0];
// ``?s={token}`` puts the page in edit mode: pre-fill from the existing
// submission and PUT instead of POST on save. ``confirmSaved`` records the
// token AND routes the URL onto it so a refresh reopens the edit page.
const { editToken, editUrl, confirmSaved } = useEditLink("f", () => slug);

const form = ref<PublicForm | null>(null);
const formTitle = computed(() =>
  form.value ? resolveText(form.value.name_nl, form.value.name_en, locale.value) : null,
);
const formDescription = computed(() =>
  form.value ? resolveText(form.value.description_nl, form.value.description_en, locale.value) : null,
);
const status = ref<"loading" | "ready" | "unavailable" | "load-failed" | "submitted" | "withdrawn">("loading");
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
  try {
    const loaded = inlined ?? (await fetchFormBySlug(slug));
    form.value = loaded;
    locale.value = pickLocale(loaded.locale);
    initAnswers(loaded);
    if (editToken) await prefillFromSubmission(loaded);
    captureBaseline();
    status.value = "ready";
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

const recoveredAt = ref<string | null>(null);

async function prefillFromSubmission(form_: PublicForm): Promise<void> {
  const sub = await fetchSubmission(editToken!);
  recoveredAt.value = sub.link_recovered_at ?? null;
  displayName.value = sub.display_name ?? "";
  for (const q of form_.questions) {
    const v = sub.answers[q.id];
    if (v === undefined) continue;
    if (q.kind === "rating" || q.kind === "number")
      answers.value[q.id] = { answer_int: typeof v === "number" ? v : null };
    else if (q.kind === "text" || q.kind === "short_text")
      answers.value[q.id] = { answer_text: typeof v === "string" ? v : "" };
    else answers.value[q.id] = { answer_choices: Array.isArray(v) ? v : [] };
  }
}

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
    if (q.kind === "rating" || q.kind === "number") next[q.id] = { answer_int: null };
    else if (q.kind === "text" || q.kind === "short_text") next[q.id] = { answer_text: "" };
    else next[q.id] = { answer_choices: [] };
  }
  answers.value = next;
}

// Dirty/revert/saved state for the shared edit bar (edit mode only).
const { dirty, justSaved, captureBaseline, revert, flashSaved } = useEditForm({
  snapshot: () => ({ name: displayName.value, answers: answers.value }),
  apply: (s) => {
    displayName.value = s.name;
    answers.value = s.answers;
  },
});

function isAnswered(q: PublicFormQuestion): boolean {
  const a = answers.value[q.id] ?? {};
  if (q.kind === "rating" || q.kind === "number") return a.answer_int != null;
  if (q.kind === "text" || q.kind === "short_text") return (a.answer_text ?? "").trim().length > 0;
  return (a.answer_choices ?? []).length > 0;
}

// --- Submit ------------------------------------------------------

const submitError = ref<string | null>(null);

/** Why a submit was refused, in words the visitor can act on: the form
 * is gone (410), or it has no places left (409). Anything else is a
 * failure to submit. */
function describeSubmitError(e: unknown): string {
  if (e instanceof ApiError && e.status === 410) return c.value.unavailable;
  if (e instanceof ApiError && e.status === 409) return c.value.full;
  return c.value.submitFail;
}

async function submit() {
  if (!form.value) return;
  if (form.value.name_required && !displayName.value.trim()) {
    showToast(c.value.nameRequired);
    return;
  }
  for (const q of form.value.questions) {
    if (q.required && !isAnswered(q)) {
      showToast(`${f.value.missingRequiredPrefix} ${q.prompt}`);
      return;
    }
  }
  submitError.value = null;
  submitting.value = true;

  const payload: SubmitAnswer[] = form.value.questions.map((q) => {
    const a = answers.value[q.id] ?? {};
    if (q.kind === "rating" || q.kind === "number")
      return { question_id: q.id, answer_int: a.answer_int ?? null };
    if (q.kind === "text" || q.kind === "short_text")
      return { question_id: q.id, answer_text: a.answer_text ?? "" };
    return { question_id: q.id, answer_choices: a.answer_choices ?? [] };
  });

  const body = { display_name: displayName.value.trim() || null, answers: payload };
  try {
    if (editToken) {
      await putSubmission(editToken, body);
      // Edit-mode save stays on the page: re-baseline + flash "Saved".
      captureBaseline();
      flashSaved();
    } else {
      const ack = await postSubmission(slug, body);
      confirmSaved(ack.edit_token);
      status.value = "submitted";
    }
  } catch (e) {
    submitError.value = describeSubmitError(e);
  } finally {
    submitting.value = false;
  }
}

async function withdraw() {
  if (!editToken) return;
  if (!window.confirm(f.value.withdrawConfirm)) return;
  submitting.value = true;
  try {
    await withdrawSubmission(editToken);
    status.value = "withdrawn";
  } catch (e) {
    submitError.value = describeSubmitError(e);
  } finally {
    submitting.value = false;
  }
}

</script>

<template>
  <PublicShell v-model:locale="locale" :hide-ads="status === 'submitted' || status === 'withdrawn'">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />
    <PublicNotice v-else-if="status === 'withdrawn'" :message="f.withdrawn" />

    <!-- On submit the whole page collapses to a single confirmation card
         (the top card is dropped) so nothing competes with saving the
         secret link. -->
    <template v-else-if="form">
      <PublicConfirmation
        v-if="status === 'submitted'"
        :url="editUrl"
        :locale="locale"
        :can-edit="form.answers_editable"
      />

      <template v-else>
        <PublicTopCard
          :title="formTitle"
          :image-url="form.image_url"
          :artist="form.image_artist_instagram"
          :credit-label="c.imageCredit"
          :description-html="formDescription"
        />
        <RecoveredNotice v-if="editToken" :recovered-at="recoveredAt" :locale="locale" />
        <Disclosure :locale="locale" />

        <form class="card stack form-card" novalidate @submit.prevent="submit">
        <!-- Closed for changes: the fields are still readable, because
             seeing what you said is the other half of what the link is
             for, but nothing here can be typed into. -->
        <fieldset class="fields" :disabled="editToken != null && !form.answers_editable">
        <!-- Pseudonym first, mirroring the events sign-up form. -->
        <input
          v-model="displayName"
          type="text"
          class="input"
          :placeholder="c.displayName"
          autocomplete="name"
          maxlength="100"
        />

        <!-- One component per kind, shared with the quiz mini-app
             (``public_shared/QuestionField.vue``). A questionnaire
             renders the whole list; a quiz renders one at a time. -->
        <QuestionField
          v-for="q in form.questions"
          :key="q.id"
          :question="q"
          :answer="answers[q.id]"
          :required-label="f.required"
          :range-hint="f.range(q.min_value, q.max_value, q.tolerance, q.step)"
          @update="(value) => (answers[q.id] = value)"
        />

        </fieldset>

        <p v-if="submitError" class="error" role="alert">{{ submitError }}</p>

        <div v-if="!editToken" class="submit-row">
          <SupportButtons />
          <button type="submit" class="btn-primary" :disabled="submitting">
            {{ submitting ? c.submitting : c.submit }}
          </button>
        </div>
        </form>
        <PublicEditBar
          v-if="editToken"
          :can-edit="form.answers_editable"
          :dirty="dirty"
          :saving="submitting"
          :just-saved="justSaved"
          :locale="locale"
          @save="submit"
          @revert="revert"
          @withdraw="withdraw"
        />
      </template>
    </template>
  </PublicShell>
</template>

<style scoped>
/* The fieldset is a grouping for the disabled state, not a layout box:
 * it hands its own children straight to the card's column. */
.fields {
  display: contents;
  border: none;
  margin: 0;
  padding: 0;
}
.form-card { display: flex; flex-direction: column; gap: 1.25rem; }
.error { color: var(--brand-red); margin: 0; }

/* --- Rating --- */

/* --- Text inputs (base ``.input`` comes from forms.css) --- */

/* --- Choice lists --- */

/* --- Submit --- */
/* .submit-row (right-aligned action row) comes from ``forms.css``. */
/* .btn-primary comes from ``src/public_shared/forms.css``. */
</style>
