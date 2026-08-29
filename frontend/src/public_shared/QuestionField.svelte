<script lang="ts" module>
export interface QuestionShape {
  id: string;
  kind: string;
  prompt: string;
  required: boolean;
  options: string[];
  low_label: string | null;
  high_label: string | null;
  min_value: number | null;
  max_value: number | null;
  step: number | null;
  tolerance: number | null;
}

export interface AnswerShape {
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
}
</script>

<script lang="ts">
/**
 * One question, rendered by its kind, for whoever is answering it.
 *
 * Lifted out of ``PublicForm``'s branch chain when quizzes arrived
 * (``docs/design-quizzes.md`` part 3.1): a questionnaire renders a list
 * of these and a quiz renders one at a time, and neither one owns the
 * six kinds. The next kind after ``number`` is added here once.
 *
 * The answer shape is the wire shape, so a parent can hand what it
 * holds straight to the submit endpoint without a transform.
 */
const {
  question,
  answer,
  requiredLabel,
  rangeHint,
  markRequired,
  onupdate,
}: {
  question: QuestionShape;
  answer: AnswerShape | undefined;
  /** Localised "required" marker text, from the mini-app's own tiny
   *  string table: this component carries no i18n of its own. */
  requiredLabel: string;
  /** The bounds of a number question, in words, from the same table.
   *  A box that silently refuses 150 is a box nobody can answer. */
  rangeHint?: string | null;
  /** Whether a required question is marked with a star. False on a
   *  quiz, where every question is required and a star on all of them
   *  marks nothing. */
  markRequired?: boolean;
  onupdate: (value: AnswerShape) => void;
} = $props();

const ratings = [1, 2, 3, 4, 5];
const chosen = $derived(answer?.answer_choices ?? []);

/** Empty box means unanswered, not zero: ``0`` is a legitimate answer
 *  to "how many", so the empty string is what maps to null. */
function setNumber(raw: string) {
  const text = raw.trim();
  const parsed = Number.parseInt(text, 10);
  onupdate({ answer_int: text === "" || Number.isNaN(parsed) ? null : parsed });
}

function toggleMulti(opt: string, on: boolean) {
  onupdate({ answer_choices: on ? [...chosen, opt] : chosen.filter((o) => o !== opt) });
}
</script>

<div class="q-block">
  <!-- A prompt names the answer as a whole, and for four of the six
       kinds that is a group of controls rather than one, so it is a
       named element the control points at rather than a ``<label>``
       wrapped around nothing. -->
  <div class="prompt" id="{question.id}-prompt">
    {question.prompt}
    {#if question.required && markRequired !== false}
      <span class="required-mark" aria-label={requiredLabel}>*</span>
    {/if}
  </div>

  {#if question.kind === "rating"}
    <div class="rating">
      <div class="rating-row" role="group" aria-labelledby="{question.id}-prompt">
        {#each ratings as v (v)}
          <button
            type="button"
            class="dot"
            class:active={answer?.answer_int === v}
            aria-label={String(v)}
            onclick={() => onupdate({ answer_int: v })}
          >
            {v}
          </button>
        {/each}
      </div>
      {#if question.low_label || question.high_label}
        <div class="legend">
          <span>{question.low_label ?? ""}</span>
          <span>{question.high_label ?? ""}</span>
        </div>
      {/if}
    </div>
  {:else if question.kind === "number"}
    <!-- One box and, when the question names one, the unit after it.
         ``inputmode`` gets the numeric keypad on a phone;
         ``type=number`` is deliberately not used, because its spinner
         and its silent scroll-to-change are worse than the keypad is
         good. -->
    <div class="number-block">
      <input
        type="text"
        inputmode="numeric"
        value={answer?.answer_int ?? ""}
        min={question.min_value ?? undefined}
        max={question.max_value ?? undefined}
        step={question.step ?? undefined}
        class="input number-input"
        aria-labelledby="{question.id}-prompt"
        oninput={(e) => setNumber((e.currentTarget as HTMLInputElement).value)}
      />
      <!-- Everything about what this box takes goes on one line under
           it, each part named. A bare value beside the box is a number
           nobody can place: "1" says nothing without the word in front
           of it. -->
      {#if rangeHint}<p class="range muted">{rangeHint}</p>{/if}
    </div>
  {:else if question.kind === "text"}
    <textarea
      value={answer?.answer_text ?? ""}
      maxlength="2000"
      rows="3"
      class="input textarea"
      aria-labelledby="{question.id}-prompt"
      oninput={(e) => onupdate({ answer_text: (e.currentTarget as HTMLTextAreaElement).value })}
    ></textarea>
  {:else if question.kind === "short_text"}
    <input
      type="text"
      value={answer?.answer_text ?? ""}
      maxlength="200"
      class="input"
      aria-labelledby="{question.id}-prompt"
      oninput={(e) => onupdate({ answer_text: (e.currentTarget as HTMLInputElement).value })}
    />
  {:else if question.kind === "single_choice"}
    <div class="choice-list" role="group" aria-labelledby="{question.id}-prompt">
      {#each question.options as opt (opt)}
        <label class="choice-row">
          <input
            type="radio"
            name="q-{question.id}"
            value={opt}
            checked={chosen[0] === opt}
            onchange={() => onupdate({ answer_choices: [opt] })}
          />
          <span>{opt}</span>
        </label>
      {/each}
    </div>
  {:else if question.kind === "multi_choice"}
    <div class="choice-list" role="group" aria-labelledby="{question.id}-prompt">
      {#each question.options as opt (opt)}
        <label class="choice-row">
          <input
            type="checkbox"
            checked={chosen.includes(opt)}
            onchange={(e) => toggleMulti(opt, (e.currentTarget as HTMLInputElement).checked)}
          />
          <span>{opt}</span>
        </label>
      {/each}
    </div>
  {/if}
</div>

<style>
.q-block {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
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
  padding: 0.625rem 0;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
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
.textarea {
  resize: vertical;
  min-height: 5rem;
}
.number-block {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.number-input {
  max-width: 8rem;
}
.range {
  margin: 0;
  font-size: 0.8125rem;
}
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
</style>
