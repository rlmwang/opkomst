<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import EditableList from "@/components/EditableList.vue";
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
  | "single_choice"
  | "multi_choice"
  | "number";

export interface QuestionDraft {
  id: string | null;
  kind: QuestionKind;
  prompt: string;
  required: boolean;
  options: string[];
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
  correct_choices: string[] | null;
  tolerance: number | null;
  /** Kompas only: which way this question moves somebody. A rating
   *  poles the statement (``pole``, the side a 5 means); a choice poles
   *  each option (``option_poles``, index-parallel to ``options``). The
   *  server drops both on the other two products. */
  pole: Pole | null;
  option_poles: Pole[] | null;
}

/** The four sides, offered as the organiser's own words. Built by the
 *  parent from the axes block, because that is where the words are. */
export interface PoleOption {
  value: Pole;
  label: string;
}

const props = defineProps<{
  modelValue: QuestionDraft;
  /** On a quiz the question also has a right answer and a value, and
   *  it is always answered: skipping one would be a free zero, so
   *  there is no switch to offer. On a questionnaire none of that
   *  exists, and the fields are not rendered rather than rendered and
   *  ignored. */
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
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: QuestionDraft): void;
  (e: "delete"): void;
  (e: "moveUp"): void;
  (e: "moveDown"): void;
}>();

const { t } = useI18n();

// Local pending option text — user types here and hits Enter (or
// the plus button) to commit one option to the list. Same UX as
// the EventForm sources/help inputs.
const newOption = ref("");

/** A quiz asks only what it can mark: both free-text kinds are out,
 *  because no rule grades a paragraph and an exact-match short answer
 *  is a quiz about spelling. Mirrors ``services/quizzes.QUIZ_KINDS``,
 *  which refuses them on save; this is why they are never offered. */
const QUIZ_KINDS: QuestionKind[] = ["single_choice", "multi_choice", "number", "rating"];
/** A kompas asks a statement you rate or a question you pick from.
 *  Nothing else: a multi-choice answer pulls three ways at once, a
 *  number has no direction, and no rule points a paragraph anywhere.
 *  Mirrors ``services/compass.COMPASS_KINDS``, which refuses the rest
 *  on save; this is why they are never offered. */
const COMPASS_KINDS: QuestionKind[] = ["rating", "single_choice"];
const FORM_KINDS: QuestionKind[] = ["rating", "short_text", "text", "single_choice", "multi_choice", "number"];

const kindOptions = computed(() =>
  (props.pointed ? COMPASS_KINDS : props.scored ? QUIZ_KINDS : FORM_KINDS).map((k) => ({
    value: k,
    label: t(`forms.question.kind.${k}`),
  })),
);

const isChoice = computed(
  () =>
    props.modelValue.kind === "single_choice" ||
    props.modelValue.kind === "multi_choice",
);
const isRating = computed(() => props.modelValue.kind === "rating");
const isNumber = computed(() => props.modelValue.kind === "number");
/** A quiz question always has a key and a value; a questionnaire's
 *  never does. The free-text kinds a quiz cannot mark are not offered
 *  in the first place (``QUIZ_KINDS``). */
const gradable = computed(() => Boolean(props.scored));
/** A kompas question has a direction and nothing else: no key, no
 *  value, and a switch for skipping that a questionnaire's has too
 *  (a skipped question is "no opinion", which the mean handles). */
const pointed = computed(() => Boolean(props.pointed));
const poleOptions = computed(() => props.poleOptions ?? []);

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
function patch<K extends keyof QuestionDraft>(key: K, value: QuestionDraft[K]): void {
  const next: QuestionDraft = { ...props.modelValue, [key]: value };
  if (key === "kind") {
    if (value !== "rating") {
      next.low_label = null;
      next.high_label = null;
    }
    if (value !== "single_choice" && value !== "multi_choice") {
      next.options = [];
    }
    if (value !== "number") {
      next.min_value = null;
      next.max_value = null;
      next.step = null;
      next.tolerance = null;
    }
    // The key is kind-shaped: keeping the old one would save a
    // rating's number as a text question's answer.
    next.correct_int = null;
    next.correct_text = null;
    next.correct_choices = null;
    // So is the direction, and for the same reason one level up: the
    // thing it was attached to did not survive the switch.
    next.pole = null;
    next.option_poles = value === "single_choice" ? next.options.map(() => null as unknown as Pole) : null;
  }
  emit("update:modelValue", next);
}

/** The key for a choice question is a subset of its own options, so it
 *  is picked rather than typed. Single choice replaces; multi toggles. */
function toggleCorrect(opt: string) {
  const current = props.modelValue.correct_choices ?? [];
  if (props.modelValue.kind === "single_choice") {
    patch("correct_choices", [opt]);
    return;
  }
  patch("correct_choices", current.includes(opt) ? current.filter((o) => o !== opt) : [...current, opt]);
}

function isCorrectOption(opt: string): boolean {
  return (props.modelValue.correct_choices ?? []).includes(opt);
}

/** The direction of one option, by its place in the list: the two
 *  arrays travel together and are filtered together on write, so the
 *  index is the link between an answer and where it points. */
function poleAt(index: number): Pole | null {
  return props.modelValue.option_poles?.[index] ?? null;
}

function setPoleAt(index: number, value: Pole): void {
  const next = [...(props.modelValue.option_poles ?? [])];
  while (next.length < props.modelValue.options.length) next.push(null as unknown as Pole);
  next[index] = value;
  patch("option_poles", next);
}

function addOption() {
  const opt = newOption.value.trim();
  if (!opt) return;
  if (props.modelValue.options.includes(opt)) {
    newOption.value = "";
    return;
  }
  const next: QuestionDraft = {
    ...props.modelValue,
    options: [...props.modelValue.options, opt],
  };
  if (pointed.value) {
    // A new option starts without a direction, which the save refuses
    // by name until the organiser picks one.
    next.option_poles = [...(props.modelValue.option_poles ?? []), null as unknown as Pole];
  }
  emit("update:modelValue", next);
  newOption.value = "";
}

function removeOption(opt: string) {
  const index = props.modelValue.options.indexOf(opt);
  const next: QuestionDraft = {
    ...props.modelValue,
    options: props.modelValue.options.filter((o) => o !== opt),
  };
  if (pointed.value && index >= 0) {
    next.option_poles = (props.modelValue.option_poles ?? []).filter((_, i) => i !== index);
  }
  // An option that no longer exists cannot be the right answer: the
  // server would refuse the save, and the organiser would have to work
  // out why. Patched into the same object rather than emitted after
  // it: a second emit reads the props this one has not landed in yet,
  // and puts the removed option back.
  if (isCorrectOption(opt)) {
    next.correct_choices = (props.modelValue.correct_choices ?? []).filter((o) => o !== opt);
  }
  emit("update:modelValue", next);
}
</script>

<template>
  <div class="question-editor">
    <div class="header-row">
      <Select
        :model-value="modelValue.kind"
        :options="kindOptions"
        option-label="label"
        option-value="value"
        class="kind-select"
        @update:model-value="(v) => patch('kind', v)"
      />
      <!-- The one thing beside the kind, and which one it is depends
           on the product: a questionnaire's question may be skipped,
           a quiz's never can, and a quiz's is worth points. Both are
           facts about the question rather than about its wording, so
           both belong on this row. -->
      <label v-if="!scored" class="required-row">
        <ToggleSwitch
          :model-value="modelValue.required"
          @update:model-value="(v) => patch('required', v)"
        />
        <span>{{ t("forms.question.required") }}</span>
      </label>
      <label v-if="gradable" class="points-field">
        <InputText
          class="points-input"
          :model-value="String(modelValue.points)"
          inputmode="numeric"
          @update:model-value="(v) => patch('points', Math.max(0, Number.parseInt((v ?? '').trim(), 10) || 0))"
        />
        <span class="muted points-label">{{ t("quizzes.question.points") }}</span>
      </label>
      <div class="header-actions">
        <Button
          type="button"
          icon="pi pi-arrow-up"
          size="small"
          severity="secondary"
          text
          :disabled="!canMoveUp"
          :aria-label="t('forms.question.moveUp')"
          @click="emit('moveUp')"
        />
        <Button
          type="button"
          icon="pi pi-arrow-down"
          size="small"
          severity="secondary"
          text
          :disabled="!canMoveDown"
          :aria-label="t('forms.question.moveDown')"
          @click="emit('moveDown')"
        />
        <Button
          type="button"
          icon="pi pi-trash"
          size="small"
          severity="secondary"
          text
          :aria-label="t('forms.question.delete')"
          @click="emit('delete')"
        />
      </div>
    </div>

    <InputText
      :model-value="modelValue.prompt"
      :placeholder="t('forms.question.promptPlaceholder')"
      fluid
      @update:model-value="(v) => patch('prompt', v ?? '')"
    />

    <!-- Rating scale captions. Both optional; an empty caption
         renders blank on the public form — the right choice for
         a generic 1..5 scale. -->
    <div v-if="isRating" class="scale-row">
      <InputText
        :model-value="modelValue.low_label ?? ''"
        :placeholder="t('forms.question.lowLabel')"
        fluid
        @update:model-value="(v) => patch('low_label', v ? v : null)"
      />
      <InputText
        :model-value="modelValue.high_label ?? ''"
        :placeholder="t('forms.question.highLabel')"
        fluid
        @update:model-value="(v) => patch('high_label', v ? v : null)"
      />
    </div>

    <!-- Which side a 5 means. The whole of what a kompas adds to a
         statement: a 5 is all the way toward this side, a 1 all the
         way toward the other end of the same axis, a 3 the middle. -->
    <label v-if="pointed && isRating" class="field pole-field">
      <span class="field-label muted">{{ t("compasses.question.polePrompt") }}</span>
      <Select
        :model-value="modelValue.pole"
        :options="poleOptions"
        option-label="label"
        option-value="value"
        :placeholder="t('compasses.question.pickPole')"
        fluid
        @update:model-value="(v) => patch('pole', v)"
      />
    </label>

    <!-- Bounds and a unit, all optional. A question with no bounds
         takes any whole number, which is the right default for "how
         old are you" and wrong for nothing.
         Labelled rather than three placeholder boxes: a placeholder is
         gone the moment there is a value, and a row of numbers with no
         words is how a stray "1" ends up being a unit. -->
    <div v-if="isNumber" class="field-row">
      <label class="field">
        <span class="field-label muted">{{ t("forms.question.minValue") }}</span>
        <InputText
          :model-value="modelValue.min_value === null ? '' : String(modelValue.min_value)"
          inputmode="numeric"
          fluid
          @update:model-value="(v) => patchNumber('min_value', v)"
        />
      </label>
      <label class="field">
        <span class="field-label muted">{{ t("forms.question.maxValue") }}</span>
        <InputText
          :model-value="modelValue.max_value === null ? '' : String(modelValue.max_value)"
          inputmode="numeric"
          fluid
          @update:model-value="(v) => patchNumber('max_value', v)"
        />
      </label>
      <label class="field">
        <span class="field-label muted">{{ t("forms.question.step") }}</span>
        <InputText
          :model-value="modelValue.step === null ? '' : String(modelValue.step)"
          inputmode="numeric"
          fluid
          @update:model-value="(v) => patchNumber('step', v)"
        />
      </label>
    </div>

    <div v-if="isChoice" class="options-block">
      <p class="muted options-label">
        {{
          pointed
            ? t("compasses.question.pickOptionPoles")
            : gradable
              ? t("quizzes.question.pickCorrect")
              : t("forms.question.options")
        }}
      </p>
      <EditableList
        :items="modelValue.options"
        :item-label="(s: string) => s"
        :item-key="(s: string) => s"
        @remove="removeOption"
      >
        <!-- On a quiz the option list is also where the right answer
             is named: a key that is one of the options should be
             picked from them, not typed again underneath. -->
        <!-- On a kompas the option list is where each answer's
             direction is chosen: the option and the side it points at
             are one decision, so they sit on one row. -->
        <template v-if="pointed" #row="{ item, index }">
          <span class="option-row option-row-pointed">
            <span class="option-text">{{ item }}</span>
            <Select
              :model-value="poleAt(index)"
              :options="poleOptions"
              option-label="label"
              option-value="value"
              :placeholder="t('compasses.question.pickPole')"
              class="option-pole-select"
              @update:model-value="(v) => setPoleAt(index, v)"
            />
          </span>
        </template>
        <template v-else-if="gradable" #row="{ item }">
          <span class="option-row">
            <button
              type="button"
              class="correct-mark"
              :class="{ 'is-correct': isCorrectOption(item) }"
              :aria-pressed="isCorrectOption(item)"
              :aria-label="t('quizzes.question.markCorrect')"
              @click="toggleCorrect(item)"
            >
              <!-- Hidden rather than removed: a tick on every option
                   says every option is right, and an icon that leaves
                   the DOM takes the row's height with it. -->
              <i class="pi pi-check" :class="{ 'is-blank': !isCorrectOption(item) }" />
            </button>
            <span>{{ item }}</span>
          </span>
        </template>
        <template #add>
          <InputText
            v-model="newOption"
            :placeholder="t('forms.question.newOption')"
            fluid
            @keydown.enter.prevent="addOption"
          />
          <Button
            type="button"
            icon="pi pi-plus"
            size="small"
            severity="secondary"
            :aria-label="t('forms.question.newOption')"
            @click="addOption"
          />
        </template>
      </EditableList>
    </div>

    <!-- The key for the kinds whose answer is a number rather than one
         of the options (``docs/design-quizzes.md`` part 1.3). A choice
         question names its answer in the option list above. -->
    <div v-if="gradable && (modelValue.kind === 'rating' || modelValue.kind === 'number')" class="field-row">
      <label class="field">
        <span class="field-label muted">{{ t("quizzes.question.correctNumber") }}</span>
        <InputText
          :model-value="modelValue.correct_int === null ? '' : String(modelValue.correct_int)"
          inputmode="numeric"
          fluid
          @update:model-value="(v) => patchNumber('correct_int', v)"
        />
      </label>
      <label v-if="modelValue.kind === 'number'" class="field">
        <span class="field-label muted">{{ t("quizzes.question.tolerance") }}</span>
        <InputText
          :model-value="modelValue.tolerance === null ? '' : String(modelValue.tolerance)"
          inputmode="numeric"
          fluid
          @update:model-value="(v) => patchNumber('tolerance', v)"
        />
      </label>
    </div>
  </div>
</template>

<style scoped>
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
.kind-select {
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
.option-pole-select {
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
.scale-row :deep(.p-inputtext) { flex: 1; }
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
.points-input {
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
.correct-mark .is-blank {
  visibility: hidden;
}
.correct-mark.is-correct {
  background: var(--brand-green-soft);
  border-color: var(--brand-green);
  color: var(--brand-green);
}
</style>
