<script lang="ts">
import SupportButtons from "@/public_shared/SupportButtons.svelte";
import Disclosure from "@/public_shared/Disclosure.svelte";
import QuestionField from "@/public_shared/QuestionField.svelte";
import PublicConfirmation from "@/public_shared/PublicConfirmation.svelte";
import PublicEditBar from "@/public_shared/PublicEditBar.svelte";
import RecoveredNotice from "@/public_shared/RecoveredNotice.svelte";
import PublicTopCard from "@/public_shared/PublicTopCard.svelte";
import PublicNotice from "@/public_shared/PublicNotice.svelte";
import PublicShell from "@/public_shared/PublicShell.svelte";
import { showToast } from "@/lib/toast";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import { useEditForm } from "@/public_shared/useEditForm.svelte";
import { useEditLink } from "@/public_shared/useEditLink.svelte";
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
// submission and PUT instead of POST on save. ``confirmSaved`` records
// the token AND routes the URL onto it so a refresh reopens the edit
// page.
const { editToken, confirmSaved, ...link } = useEditLink("f", () => slug);

let form = $state<PublicForm | null>(null);
let status = $state<"loading" | "ready" | "unavailable" | "load-failed" | "submitted" | "withdrawn">("loading");
let submitting = $state(false);
let locale = $state<Locale>("nl");

const formTitle = $derived(form ? resolveText(form.name_nl, form.name_en, locale) : null);
const formDescription = $derived(
  form ? resolveText(form.description_nl, form.description_en, locale) : null,
);
const c = $derived(chromeStrings(locale));
const f = $derived(formStrings(locale));

// Optional pseudonym (real or not), the same contract as the events
// sign-up name. Empty means anonymous.
let displayName = $state("");

let recoveredAt = $state<string | null>(null);

// --- Answer state ------------------------------------------------

type Answer = {
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
};
let answers = $state<Record<string, Answer>>({});

function initAnswers(form_: PublicForm): void {
  const next: Record<string, Answer> = {};
  for (const q of form_.questions) {
    if (q.kind === "rating" || q.kind === "number") next[q.id] = { answer_int: null };
    else if (q.kind === "text" || q.kind === "short_text") next[q.id] = { answer_text: "" };
    else next[q.id] = { answer_choices: [] };
  }
  answers = next;
}

async function prefillFromSubmission(form_: PublicForm): Promise<void> {
  const sub = await fetchSubmission(editToken!);
  recoveredAt = sub.link_recovered_at ?? null;
  displayName = sub.display_name ?? "";
  for (const q of form_.questions) {
    const v = sub.answers[q.id];
    if (v === undefined) continue;
    if (q.kind === "rating" || q.kind === "number")
      answers[q.id] = { answer_int: typeof v === "number" ? v : null };
    else if (q.kind === "text" || q.kind === "short_text")
      answers[q.id] = { answer_text: typeof v === "string" ? v : "" };
    else answers[q.id] = { answer_choices: Array.isArray(v) ? v : [] };
  }
}

// Dirty/revert/saved state for the shared edit bar (edit mode only).
const edit = useEditForm({
  snapshot: () => ({ name: displayName, answers }),
  apply: (s) => {
    displayName = s.name;
    answers = s.answers;
  },
});

async function load() {
  const inlined = window.__OPKOMST_FORM__;
  if (inlined === null) {
    status = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchFormBySlug(slug));
    form = loaded;
    locale = pickLocale(loaded.locale);
    initAnswers(loaded);
    if (editToken) await prefillFromSubmission(loaded);
    edit.captureBaseline();
    status = "ready";
  } catch (e) {
    status = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
}
void load();

function isAnswered(q: PublicFormQuestion): boolean {
  const a = answers[q.id] ?? {};
  if (q.kind === "rating" || q.kind === "number") return a.answer_int != null;
  if (q.kind === "text" || q.kind === "short_text") return (a.answer_text ?? "").trim().length > 0;
  return (a.answer_choices ?? []).length > 0;
}

// --- Submit ------------------------------------------------------

let submitError = $state<string | null>(null);

/** Why a submit was refused, in words the visitor can act on: the form
 * is gone (410), or it has no places left (409). Anything else is a
 * failure to submit. */
function describeSubmitError(e: unknown): string {
  if (e instanceof ApiError && e.status === 410) return c.unavailable;
  if (e instanceof ApiError && e.status === 409) return c.full;
  return c.submitFail;
}

async function submit() {
  if (!form) return;
  if (form.name_required && !displayName.trim()) {
    showToast(c.nameRequired);
    return;
  }
  for (const q of form.questions) {
    if (q.required && !isAnswered(q)) {
      showToast(`${f.missingRequiredPrefix} ${q.prompt}`);
      return;
    }
  }
  submitError = null;
  submitting = true;

  const payload: SubmitAnswer[] = form.questions.map((q) => {
    const a = answers[q.id] ?? {};
    if (q.kind === "rating" || q.kind === "number")
      return { question_id: q.id, answer_int: a.answer_int ?? null };
    if (q.kind === "text" || q.kind === "short_text")
      return { question_id: q.id, answer_text: a.answer_text ?? "" };
    return { question_id: q.id, answer_choices: a.answer_choices ?? [] };
  });

  const body = { display_name: displayName.trim() || null, answers: payload };
  try {
    if (editToken) {
      await putSubmission(editToken, body);
      // Edit-mode save stays on the page: re-baseline and flash "Saved".
      edit.captureBaseline();
      edit.flashSaved();
    } else {
      const ack = await postSubmission(slug, body);
      confirmSaved(ack.edit_token);
      status = "submitted";
    }
  } catch (e) {
    submitError = describeSubmitError(e);
  } finally {
    submitting = false;
  }
}

async function withdraw() {
  if (!editToken) return;
  if (!window.confirm(f.withdrawConfirm)) return;
  submitting = true;
  try {
    await withdrawSubmission(editToken);
    status = "withdrawn";
  } catch (e) {
    submitError = describeSubmitError(e);
  } finally {
    submitting = false;
  }
}
</script>

<PublicShell bind:locale hideAds={status === "submitted" || status === "withdrawn"}>
  {#if status === "loading"}
    <PublicNotice message={c.loading} />
  {:else if status === "unavailable"}
    <PublicNotice message={c.unavailable} />
  {:else if status === "load-failed"}
    <PublicNotice message={c.loadFailed} />
  {:else if status === "withdrawn"}
    <PublicNotice message={f.withdrawn} />
  {:else if form}
    <!-- On submit the whole page collapses to a single confirmation card
         (the top card is dropped) so nothing competes with saving the
         secret link. -->
    {#if status === "submitted"}
      <PublicConfirmation url={link.editUrl} {locale} canEdit={form.answers_editable} />
    {:else}
      <PublicTopCard
        title={formTitle}
        imageUrl={form.image_url}
        artist={form.image_artist_instagram}
        creditLabel={c.imageCredit}
        descriptionHtml={formDescription}
      />
      {#if editToken}<RecoveredNotice {recoveredAt} {locale} />{/if}
      <Disclosure {locale} />

      <form class="card stack form-card" novalidate onsubmit={(e) => { e.preventDefault(); void submit(); }}>
        <!-- Closed for changes: the fields are still readable, because
             seeing what you said is the other half of what the link is
             for, but nothing here can be typed into. -->
        <fieldset class="fields" disabled={editToken != null && !form.answers_editable}>
          <!-- Pseudonym first, mirroring the events sign-up form. -->
          <input
            bind:value={displayName}
            type="text"
            class="input"
            placeholder={c.displayName}
            autocomplete="name"
            maxlength="100"
          />

          <!-- One component per kind, shared with the quiz mini-app
               (``public_shared/QuestionField.svelte``). A questionnaire
               renders the whole list; a quiz renders one at a time. -->
          {#each form.questions as q (q.id)}
            <QuestionField
              question={q}
              answer={answers[q.id]}
              requiredLabel={f.required}
              rangeHint={f.range(q.min_value, q.max_value, q.tolerance, q.step)}
              onupdate={(value) => (answers[q.id] = value)}
            />
          {/each}
        </fieldset>

        {#if submitError}<p class="error" role="alert">{submitError}</p>{/if}

        {#if !editToken}
          <div class="submit-row">
            <SupportButtons />
            <button type="submit" class="btn-primary" disabled={submitting}>
              {submitting ? c.submitting : c.submit}
            </button>
          </div>
        {/if}
      </form>

      {#if editToken}
        <PublicEditBar
          canEdit={form.answers_editable}
          dirty={edit.dirty}
          saving={submitting}
          justSaved={edit.justSaved}
          {locale}
          onsave={submit}
          onrevert={edit.revert}
          onwithdraw={withdraw}
        />
      {/if}
    {/if}
  {/if}
</PublicShell>

<style>
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
/* .submit-row (right-aligned action row) comes from ``form.css``. */
/* .btn-primary comes from ``src/public_shared/forms.css``. */
</style>
