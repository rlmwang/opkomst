<script lang="ts" module>
import type { Pole } from "@/api/types";

/**
 * Editor for one question on a Form. The shape mirrors the
 * backend's ``FormQuestionIn`` exactly so a parent page collecting
 * an array of these ships them as ``questions`` on the create or
 * update payload without a transform step. ``id`` is null for
 * newly-added drafts; existing questions carry their server-
 * assigned uuid so the diff-apply matches by id.
 */
export type QuestionKind =
  | "rating"
  | "text"
  | "short_text"
  | "multiple_choice"
  | "multiple_answer"
  | "number";

/**
 * One choice on a question. ``id`` is null for a newly typed option and
 * carries the server's uuid for one that already exists, which is what
 * keeps the answers to it attached across a rename or a reorder. An
 * editor that drops the id is asking for the option to be replaced and
 * its answers deleted (``docs/design-question-edits.md``).
 */
export interface OptionDraft {
  id: string | null;
  label: string;
  /** Kompas only: which way picking this moves somebody. */
  pole: Pole | null;
  /** Quiz only: part of the answer key. */
  is_correct: boolean;
}

export interface QuestionDraft {
  id: string | null;
  kind: QuestionKind;
  prompt: string;
  required: boolean;
  options: OptionDraft[];
  low_label: string | null;
  high_label: string | null;
  /** ``number`` only, and all three say which numbers count as an
   *  answer: the bounds it sits between and the step it lands on.
   *  All optional. */
  min_value: number | null;
  max_value: number | null;
  step: number | null;
  /** Quiz only: what a correct answer is worth, and what it is. The
   *  server drops all five on a questionnaire. */
  points: number;
  correct_int: number | null;
  correct_text: string | null;
  tolerance: number | null;
  /** Kompas only: which way this question moves somebody. A rating
   *  poles the statement, and that is this field: the side a 5 means. A
   *  choice poles each option, so its side rides on the option itself.
   *  The server drops both on the other two products. */
  pole: Pole | null;
}

/** The four sides, offered as the organiser's own words. Built by the
 *  parent from the axes block, because that is where the words are. */
export interface PoleOption {
  value: Pole;
  label: string;
}
</script>

<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppIcon from "@/components/AppIcon.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppToggle from "@/components/AppToggle.svelte";
import EditableList from "@/components/EditableList.svelte";
import SelectField from "@/components/SelectField.svelte";
import { t } from "@/i18n.svelte";

let {
  value = $bindable(),
  scored,
  pointed,
  poleOptions,
  canMoveUp,
  canMoveDown,
  ondelete,
  onmoveUp,
  onmoveDown,
}: {
  value: QuestionDraft;
  /** On a quiz the question also has a right answer and a value, and it
   *  is always answered: skipping one would be a free zero, so there is
   *  no switch to offer. On a questionnaire none of that exists, and
   *  the fields are not rendered rather than rendered and ignored. */
  scored?: boolean;
  /** On a kompas every answer carries a direction, and which half of
   *  the question carries it depends on the kind: a statement poles
   *  itself, a choice poles each option. There is no key and no value,
   *  so neither is rendered. */
  pointed?: boolean;
  /** The four sides in the organiser's own words, from the axes block
   *  above. Empty until the axes are named, which is what the select's
   *  placeholder then says. */
  poleOptions?: PoleOption[];
  /** Hide the "move up" button on the first row. */
  canMoveUp: boolean;
  /** Hide the "move down" button on the last row. */
  canMoveDown: boolean;
  ondelete: () => void;
  onmoveUp: () => void;
  onmoveDown: () => void;
} = $props();

// Local pending option text — user types here and hits Enter (or
// the plus button) to commit one option to the list. Same UX as
// the EventForm sources/help inputs.
let newOption = $state("");

/** A quiz asks only what it can mark: both free-text kinds are out,
 *  because no rule grades a paragraph and an exact-match short answer
 *  is a quiz about spelling. Mirrors ``services/quizzes.QUIZ_KINDS``,
 *  which refuses them on save; this is why they are never offered. */
const QUIZ_KINDS: QuestionKind[] = ["multiple_choice", "multiple_answer", "number", "rating"];
/** A kompas asks a statement you rate or a question you pick from.
 *  Nothing else: a multi-choice answer pulls three ways at once, a
 *  number has no direction, and no rule points a paragraph anywhere.
 *  Mirrors ``services/compass.COMPASS_KINDS``, which refuses the rest
 *  on save; this is why they are never offered. */
const COMPASS_KINDS: QuestionKind[] = ["rating", "multiple_choice"];
const FORM_KINDS: QuestionKind[] = ["rating", "short_text", "text", "multiple_choice", "multiple_answer", "number"];

const kindOptions = $derived(
  (pointed ? COMPASS_KINDS : scored ? QUIZ_KINDS : FORM_KINDS).map((k) => ({
    value: k,
    label: t(`form.question.kind.${k}`),
  })),
);

const isChoice = $derived(value.kind === "multiple_choice" || value.kind === "multiple_answer");
const isRating = $derived(value.kind === "rating");
const isNumber = $derived(value.kind === "number");
/** A quiz question always has a key and a value; a questionnaire's
 *  never does. The free-text kinds a quiz cannot mark are not offered
 *  in the first place (``QUIZ_KINDS``). */
const gradable = $derived(Boolean(scored));
/** A kompas question has a direction and nothing else: no key, no
 *  value, and a switch for skipping that a questionnaire's has too
 *  (a skipped question is "no opinion", which the mean handles). */
const poles = $derived(poleOptions ?? []);

/** Empty box → no bound. ``0`` is a legitimate bound, so the check is
 *  against the empty string rather than falsiness. */
function patchNumber(
  key: "min_value" | "max_value" | "correct_int" | "tolerance" | "step",
  raw: string | null | undefined,
): void {
  const text = (raw ?? "").trim();
  const parsed = Number.parseInt(text, 10);
  patch(key, text === "" || Number.isNaN(parsed) ? null : parsed);
}

/** Builds a new QuestionDraft with one field patched and kind-
 * incompatible fields reset. Switching from rating to choice
 * would otherwise carry low/high labels silently into the
 * payload (ignored server-side but noisy); the other direction
 * would orphan an options list. */
function patch<K extends keyof QuestionDraft>(key: K, patched: QuestionDraft[K]): void {
  const next: QuestionDraft = { ...value, [key]: patched };
  if (key === "kind") {
    if (patched !== "rating") {
      next.low_label = null;
      next.high_label = null;
    }
    if (patched !== "multiple_choice" && patched !== "multiple_answer") {
      next.options = [];
    }
    if (patched !== "number") {
      next.min_value = null;
      next.max_value = null;
      next.step = null;
      next.tolerance = null;
    }
    // The key is kind-shaped: keeping the old one would save a
    // rating's number as a text question's answer.
    next.correct_int = null;
    next.correct_text = null;
    // So is the direction, and for the same reason one level up: the
    // thing it was attached to did not survive the switch. Both live on
    // the options now, so they are cleared there.
    next.pole = null;
    next.options = next.options.map((o) => ({ ...o, pole: null, is_correct: false }));
  }
  value = next;
}

/** Patch one option in place, leaving its id alone. Every edit to a
 *  choice goes through here, which is what keeps the answers to it
 *  attached: a rename is a new ``label`` on the same row, never a new
 *  row. */
function patchOption(index: number, fields: Partial<OptionDraft>): void {
  patch(
    "options",
    value.options.map((o, i) => (i === index ? { ...o, ...fields } : o)),
  );
}

/** The key for a choice question is which of its options are right, so
 *  it is picked rather than typed. Single choice replaces; multi
 *  toggles. */
function toggleCorrect(index: number) {
  if (value.kind === "multiple_choice") {
    patch(
      "options",
      value.options.map((o, i) => ({ ...o, is_correct: i === index })),
    );
    return;
  }
  patchOption(index, { is_correct: !value.options[index].is_correct });
}

function addOption() {
  const label = newOption.trim();
  if (!label) return;
  if (value.options.some((o) => o.label === label)) {
    newOption = "";
    return;
  }
  // No id: this one is new, and the server mints it. A new option
  // starts without a direction, which the save refuses by name until
  // the organiser picks one.
  value = {
    ...value,
    options: [...value.options, { id: null, label, pole: null, is_correct: false }],
  };
  newOption = "";
}

function removeOption(option: OptionDraft) {
  // Removing an option removes what was answered with it. The save says
  // so and asks again (``docs/design-question-edits.md``); nothing has
  // to be untangled here, because the key and the direction went with
  // the row.
  value = { ...value, options: value.options.filter((o) => o !== option) };
}
</script>

<div class="question-editor">
  <div class="header-row">
    <SelectField
      bind:value={() => value.kind, (v) => patch("kind", v as QuestionKind)}
      options={kindOptions}
      optionLabel="label"
      optionValue="value"
      class="kind-select"
    />
    <!-- The one thing beside the kind, and which one it is depends on
         the product: a questionnaire's question may be skipped, a
         quiz's never can, and a quiz's is worth points. Both are facts
         about the question rather than about its wording, so both
         belong on this row. -->
    {#if !scored}
      <label class="required-row">
        <AppToggle bind:checked={() => value.required, (v) => patch("required", v)} />
        <span>{t("form.question.required")}</span>
      </label>
    {/if}
    {#if gradable}
      <label class="points-field">
        <AppInput
          class="points-input"
          value={String(value.points)}
          inputmode="numeric"
          oninput={(e) =>
            patch(
              "points",
              Math.max(0, Number.parseInt((e.currentTarget as HTMLInputElement).value.trim(), 10) || 0),
            )}
        />
        <span class="muted points-label">{t("quiz.question.points")}</span>
      </label>
    {/if}
    <div class="header-actions">
      <AppButton
        type="button"
        icon="arrow-up"
        size="small"
        severity="secondary"
        text
        disabled={!canMoveUp}
        ariaLabel={t("form.question.moveUp")}
        onclick={onmoveUp}
      />
      <AppButton
        type="button"
        icon="arrow-down"
        size="small"
        severity="secondary"
        text
        disabled={!canMoveDown}
        ariaLabel={t("form.question.moveDown")}
        onclick={onmoveDown}
      />
      <AppButton
        type="button"
        icon="trash"
        size="small"
        severity="secondary"
        text
        ariaLabel={t("form.question.delete")}
        onclick={ondelete}
      />
    </div>
  </div>

  <AppInput
    value={value.prompt}
    placeholder={t("form.question.promptPlaceholder")}
    fluid
    oninput={(e) => patch("prompt", (e.currentTarget as HTMLInputElement).value)}
  />

  <!-- Rating scale captions. Both optional; an empty caption renders
       blank on the public form, which is the right choice for a generic
       1..5 scale. -->
  {#if isRating}
    <div class="scale-row">
      <AppInput
        value={value.low_label ?? ""}
        placeholder={t("form.question.lowLabel")}
        fluid
        oninput={(e) => {
          const v = (e.currentTarget as HTMLInputElement).value;
          patch("low_label", v ? v : null);
        }}
      />
      <AppInput
        value={value.high_label ?? ""}
        placeholder={t("form.question.highLabel")}
        fluid
        oninput={(e) => {
          const v = (e.currentTarget as HTMLInputElement).value;
          patch("high_label", v ? v : null);
        }}
      />
    </div>
  {/if}

  <!-- Which side a 5 means. The whole of what a kompas adds to a
       statement: a 5 is all the way toward this side, a 1 all the way
       toward the other end of the same axis, a 3 the middle. -->
  {#if pointed && isRating}
    <label class="field pole-field">
      <span class="field-label muted">{t("compass.question.polePrompt")}</span>
      <SelectField
        bind:value={() => value.pole, (v) => patch("pole", v as Pole)}
        options={poles}
        optionLabel="label"
        optionValue="value"
        placeholder={t("compass.question.pickPole")}
        fluid
      />
    </label>
  {/if}

  <!-- Bounds and a step, all optional. A question with no bounds takes
       any whole number, which is the right default for "how old are
       you" and wrong for nothing.
       Labelled rather than three placeholder boxes: a placeholder is
       gone the moment there is a value, and a row of numbers with no
       words is how a stray "1" ends up being a unit. -->
  {#if isNumber}
    <div class="field-row">
      <label class="field">
        <span class="field-label muted">{t("form.question.minValue")}</span>
        <AppInput
          value={value.min_value === null ? "" : String(value.min_value)}
          inputmode="numeric"
          fluid
          oninput={(e) => patchNumber("min_value", (e.currentTarget as HTMLInputElement).value)}
        />
      </label>
      <label class="field">
        <span class="field-label muted">{t("form.question.maxValue")}</span>
        <AppInput
          value={value.max_value === null ? "" : String(value.max_value)}
          inputmode="numeric"
          fluid
          oninput={(e) => patchNumber("max_value", (e.currentTarget as HTMLInputElement).value)}
        />
      </label>
      <label class="field">
        <span class="field-label muted">{t("form.question.step")}</span>
        <AppInput
          value={value.step === null ? "" : String(value.step)}
          inputmode="numeric"
          fluid
          oninput={(e) => patchNumber("step", (e.currentTarget as HTMLInputElement).value)}
        />
      </label>
    </div>
  {/if}

  {#if isChoice}
    <div class="options-block">
      <p class="muted options-label">
        {pointed
          ? t("compass.question.pickOptionPoles")
          : gradable
            ? t("quiz.question.pickCorrect")
            : t("form.question.options")}
      </p>
      <EditableList
        items={value.options}
        itemLabel={(o: OptionDraft) => o.label}
        itemKey={(o: OptionDraft) => o.id ?? o.label}
        onremove={removeOption}
      >
        <!-- On a quiz the option list is also where the right answer is
             named: a key that is one of the options should be picked
             from them, not typed again underneath.
             On a kompas the option list is where each answer's
             direction is chosen: the option and the side it points at
             are one decision, so they sit on one row. -->
        {#snippet row({ item, index })}
          {#if pointed}
            <span class="option-row option-row-pointed">
              <span class="option-text">{item.label}</span>
              <SelectField
                bind:value={() => item.pole, (v) => patchOption(index, { pole: v as Pole })}
                options={poles}
                optionLabel="label"
                optionValue="value"
                placeholder={t("compass.question.pickPole")}
                class="option-pole-select"
              />
            </span>
          {:else if gradable}
            <span class="option-row">
              <button
                type="button"
                class="correct-mark"
                class:is-correct={item.is_correct}
                aria-pressed={item.is_correct}
                aria-label={t("quiz.question.markCorrect")}
                onclick={() => toggleCorrect(index)}
              >
                <!-- Hidden rather than removed: a tick on every option
                     says every option is right, and an icon that leaves
                     the DOM takes the row's height with it. -->
                <AppIcon name="check" class={item.is_correct ? "" : "is-blank"} />
              </button>
              <span>{item.label}</span>
            </span>
          {:else}
            <span>{item.label}</span>
          {/if}
        {/snippet}
        {#snippet add()}
          <AppInput
            bind:value={newOption}
            placeholder={t("form.question.newOption")}
            fluid
            onkeydown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addOption();
              }
            }}
          />
          <AppButton
            type="button"
            icon="plus"
            size="small"
            severity="secondary"
            ariaLabel={t("form.question.newOption")}
            onclick={addOption}
          />
        {/snippet}
      </EditableList>
    </div>
  {/if}

  <!-- The key for the kinds whose answer is a number rather than one of
       the options (``docs/design-quizzes.md`` part 1.3). A choice
       question names its answer in the option list above. -->
  {#if gradable && (value.kind === "rating" || value.kind === "number")}
    <div class="field-row">
      <label class="field">
        <span class="field-label muted">{t("quiz.question.correctNumber")}</span>
        <AppInput
          value={value.correct_int === null ? "" : String(value.correct_int)}
          inputmode="numeric"
          fluid
          oninput={(e) => patchNumber("correct_int", (e.currentTarget as HTMLInputElement).value)}
        />
      </label>
      {#if value.kind === "number"}
        <label class="field">
          <span class="field-label muted">{t("quiz.question.tolerance")}</span>
          <AppInput
            value={value.tolerance === null ? "" : String(value.tolerance)}
            inputmode="numeric"
            fluid
            oninput={(e) => patchNumber("tolerance", (e.currentTarget as HTMLInputElement).value)}
          />
        </label>
      {/if}
    </div>
  {/if}
</div>

<style>
.question-editor {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 0.875rem 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
}
.header-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
:global(.kind-select) {
  min-width: 12rem;
}
.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.125rem;
}
.required-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  flex-shrink: 0;
}
.option-row-pointed {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}
.option-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
}
:global(.option-pole-select) {
  flex: 0 0 auto;
  min-width: 11rem;
}
.pole-field {
  max-width: 22rem;
}
.scale-row {
  display: flex;
  gap: 0.5rem;
}
.scale-row :deep(.app-input) { flex: 1; }
.options-block {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.options-label {
  margin: 0;
  font-size: 0.8125rem;
}
/* Labelled fields in a row: the label stays when the box has a value,
 * which a placeholder does not. */
.field-row {
  display: flex;
  gap: 0.5rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.1875rem;
  flex: 1;
  min-width: 0;
}
.field-label {
  font-size: 0.75rem;
}
.points-field {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  flex-shrink: 0;
}
:global(.points-input) {
  max-width: 4.5rem;
}
.points-label {
  font-size: 0.875rem;
}
/* The tick that marks an option as the right answer. Off it is an
 * outline; on it fills. Full opacity in both states: a control that
 * only appears on hover is a control nobody finds. */
.option-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.correct-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  flex-shrink: 0;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: transparent;
  color: var(--brand-text-muted);
  cursor: pointer;
}
.correct-mark :global(.is-blank) {
  visibility: hidden;
}
.correct-mark.is-correct {
  background: var(--brand-green-soft);
  border-color: var(--brand-green);
  color: var(--brand-green);
}
</style>
