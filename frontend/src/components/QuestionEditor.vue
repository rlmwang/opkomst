<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import EditableList from "@/components/EditableList.vue";

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
  /** ``number`` only: the bounds an answer has to sit inside, and the
   *  word rendered after the box ("jaar", "km"). All optional. */
  min_value: number | null;
  max_value: number | null;
  unit: string | null;
  /** Quiz only: what a correct answer is worth, and what it is. The
   *  server drops all five on a questionnaire. */
  points: number;
  correct_int: number | null;
  correct_text: string | null;
  correct_choices: string[] | null;
  tolerance: number | null;
}

const props = defineProps<{
  modelValue: QuestionDraft;
  /** On a quiz the question also has a right answer and a value. On a
   *  questionnaire neither exists, and the fields are not rendered
   *  rather than rendered and ignored. */
  scored?: boolean;
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

const kindOptions = computed(() =>
  (["rating", "short_text", "text", "single_choice", "multi_choice", "number"] as QuestionKind[]).map(
    (k) => ({ value: k, label: t(`forms.question.kind.${k}`) }),
  ),
);

const isChoice = computed(
  () =>
    props.modelValue.kind === "single_choice" ||
    props.modelValue.kind === "multi_choice",
);
const isRating = computed(() => props.modelValue.kind === "rating");
const isNumber = computed(() => props.modelValue.kind === "number");
/** No rule grades a paragraph, so a long-text question is asked and
 *  never scored, whatever the quiz says. */
const gradable = computed(() => Boolean(props.scored) && props.modelValue.kind !== "text");

/** Empty box → no bound. ``0`` is a legitimate bound, so the check is
 *  against the empty string rather than falsiness. */
function patchNumber(key: "min_value" | "max_value" | "correct_int" | "tolerance", raw: string | null | undefined): void {
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
      next.unit = null;
      next.tolerance = null;
    }
    // The key is kind-shaped: keeping the old one would save a
    // rating's number as a text question's answer.
    next.correct_int = null;
    next.correct_text = null;
    next.correct_choices = null;
    if (value === "text") next.points = 0;
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

function addOption() {
  const opt = newOption.value.trim();
  if (!opt) return;
  if (props.modelValue.options.includes(opt)) {
    newOption.value = "";
    return;
  }
  patch("options", [...props.modelValue.options, opt]);
  newOption.value = "";
}

function removeOption(opt: string) {
  patch(
    "options",
    props.modelValue.options.filter((o) => o !== opt),
  );
  // An option that no longer exists cannot be the right answer: the
  // server would refuse the save, and the organiser would have to work
  // out why.
  if (isCorrectOption(opt)) {
    patch(
      "correct_choices",
      (props.modelValue.correct_choices ?? []).filter((o) => o !== opt),
    );
  }
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

    <!-- For a number the bounds and the unit are what the question
         *is*, so the switch that only says whether it may be skipped
         belongs under them rather than between the prompt and its
         own configuration. ``order`` rather than a second copy of the
         markup: the card is already a flex column. -->
    <label class="required-row" :class="{ 'required-last': isNumber }">
      <ToggleSwitch
        :model-value="modelValue.required"
        @update:model-value="(v) => patch('required', v)"
      />
      <span>{{ t("forms.question.required") }}</span>
    </label>

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

    <!-- Bounds and a unit, all optional. A question with no bounds
         takes any whole number, which is the right default for "how
         old are you" and wrong for nothing. -->
    <div v-if="isNumber" class="scale-row">
      <InputText
        :model-value="modelValue.min_value === null ? '' : String(modelValue.min_value)"
        :placeholder="t('forms.question.minValue')"
        inputmode="numeric"
        fluid
        @update:model-value="(v) => patchNumber('min_value', v)"
      />
      <InputText
        :model-value="modelValue.max_value === null ? '' : String(modelValue.max_value)"
        :placeholder="t('forms.question.maxValue')"
        inputmode="numeric"
        fluid
        @update:model-value="(v) => patchNumber('max_value', v)"
      />
      <InputText
        :model-value="modelValue.unit ?? ''"
        :placeholder="t('forms.question.unit')"
        fluid
        @update:model-value="(v) => patch('unit', v ? v : null)"
      />
    </div>

    <div v-if="isChoice" class="options-block">
      <p class="muted options-label">{{ gradable ? t("quizzes.question.pickCorrect") : t("forms.question.options") }}</p>
      <EditableList
        :items="modelValue.options"
        :item-label="(s: string) => s"
        :item-key="(s: string) => s"
        @remove="removeOption"
      >
        <!-- On a quiz the option list is also where the right answer
             is named: a key that is one of the options should be
             picked from them, not typed again underneath. -->
        <template v-if="gradable" #row="{ item }">
          <span class="option-row">
            <button
              type="button"
              class="correct-mark"
              :class="{ 'is-correct': isCorrectOption(item) }"
              :aria-pressed="isCorrectOption(item)"
              :aria-label="t('quizzes.question.markCorrect')"
              @click="toggleCorrect(item)"
            >
              <i class="pi pi-check" />
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

    <!-- The rest of the key, for the kinds whose answer is typed
         rather than picked, plus what the question is worth. Quiz
         only, and never on a long-text question: no rule grades a
         paragraph (``docs/design-quizzes.md`` part 1.3). -->
    <div v-if="gradable" class="key-row">
      <InputText
        v-if="modelValue.kind === 'short_text'"
        :model-value="modelValue.correct_text ?? ''"
        :placeholder="t('quizzes.question.correctText')"
        fluid
        @update:model-value="(v) => patch('correct_text', v ? v : null)"
      />
      <InputText
        v-if="modelValue.kind === 'rating' || modelValue.kind === 'number'"
        :model-value="modelValue.correct_int === null ? '' : String(modelValue.correct_int)"
        :placeholder="t('quizzes.question.correctNumber')"
        inputmode="numeric"
        fluid
        @update:model-value="(v) => patchNumber('correct_int', v)"
      />
      <InputText
        v-if="modelValue.kind === 'number'"
        :model-value="modelValue.tolerance === null ? '' : String(modelValue.tolerance)"
        :placeholder="t('quizzes.question.tolerance')"
        inputmode="numeric"
        fluid
        @update:model-value="(v) => patchNumber('tolerance', v)"
      />
      <!-- A placeholder disappears the moment there is a value, and a
           bare box with "2" in it says nothing. The word stays. -->
      <label class="points-field">
        <InputText
          class="points-input"
          :model-value="String(modelValue.points)"
          inputmode="numeric"
          @update:model-value="(v) => patch('points', Math.max(0, Number.parseInt((v ?? '').trim(), 10) || 0))"
        />
        <span class="muted points-label">{{ t("quizzes.question.points") }}</span>
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
.required-last {
  order: 1;
}
.required-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  /* Inline so the toggle and its label sit on one line; the
   * surrounding question card's gap takes care of vertical
   * breathing room. */
  align-self: flex-start;
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
.key-row {
  display: flex;
  gap: 0.5rem;
}
.key-row :deep(.p-inputtext) { flex: 1; }
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
.correct-mark.is-correct {
  background: var(--brand-green-soft);
  border-color: var(--brand-green);
  color: var(--brand-green);
}
</style>
