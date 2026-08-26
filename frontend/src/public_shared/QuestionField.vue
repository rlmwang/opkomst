<script setup lang="ts">
/**
 * One question, rendered by its kind, for whoever is answering it.
 *
 * Lifted out of ``PublicForm``'s ``v-if`` chain when quizzes arrived
 * (``docs/design-quizzes.md`` part 3.1): a questionnaire renders a list
 * of these and a quiz renders one at a time, and neither one owns the
 * six kinds. The next kind after ``number`` is added here once.
 *
 * The answer shape is the wire shape, so a parent can hand what it
 * holds straight to the submit endpoint without a transform.
 */
import { computed } from "vue";

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
  unit: string | null;
}

export interface AnswerShape {
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
}

const props = defineProps<{
  question: QuestionShape;
  answer: AnswerShape | undefined;
  /** Localised "required" marker text, from the mini-app's own tiny
   *  string table: this component carries no i18n of its own. */
  requiredLabel: string;
}>();

const emit = defineEmits<{ (e: "update", value: AnswerShape): void }>();

const ratings = [1, 2, 3, 4, 5];
const chosen = computed(() => props.answer?.answer_choices ?? []);

/** Empty box means unanswered, not zero: ``0`` is a legitimate answer
 *  to "how many", so the empty string is what maps to null. */
function setNumber(raw: string) {
  const text = raw.trim();
  const parsed = Number.parseInt(text, 10);
  emit("update", { answer_int: text === "" || Number.isNaN(parsed) ? null : parsed });
}

function toggleMulti(opt: string, on: boolean) {
  emit("update", { answer_choices: on ? [...chosen.value, opt] : chosen.value.filter((o) => o !== opt) });
}
</script>

<template>
  <div class="q-block">
    <label class="prompt">
      {{ question.prompt }}
      <span v-if="question.required" class="required-mark" :aria-label="requiredLabel">*</span>
    </label>

    <div v-if="question.kind === 'rating'" class="rating">
      <div class="rating-row">
        <button
          v-for="v in ratings"
          :key="v"
          type="button"
          class="dot"
          :class="{ active: answer?.answer_int === v }"
          :aria-label="String(v)"
          @click="emit('update', { answer_int: v })"
        >
          {{ v }}
        </button>
      </div>
      <div v-if="question.low_label || question.high_label" class="legend">
        <span>{{ question.low_label ?? "" }}</span>
        <span>{{ question.high_label ?? "" }}</span>
      </div>
    </div>

    <!-- One box and, when the question names one, the unit after it.
         ``inputmode`` gets the numeric keypad on a phone;
         ``type=number`` is deliberately not used, because its spinner
         and its silent scroll-to-change are worse than the keypad is
         good. -->
    <div v-else-if="question.kind === 'number'" class="number-row">
      <input
        type="text"
        inputmode="numeric"
        :value="answer?.answer_int ?? ''"
        :min="question.min_value ?? undefined"
        :max="question.max_value ?? undefined"
        class="input number-input"
        @input="(e) => setNumber((e.target as HTMLInputElement).value)"
      />
      <span v-if="question.unit" class="unit muted">{{ question.unit }}</span>
    </div>

    <textarea
      v-else-if="question.kind === 'text'"
      :value="answer?.answer_text ?? ''"
      maxlength="2000"
      rows="3"
      class="input textarea"
      @input="(e) => emit('update', { answer_text: (e.target as HTMLTextAreaElement).value })"
    />

    <input
      v-else-if="question.kind === 'short_text'"
      type="text"
      :value="answer?.answer_text ?? ''"
      maxlength="200"
      class="input"
      @input="(e) => emit('update', { answer_text: (e.target as HTMLInputElement).value })"
    />

    <div v-else-if="question.kind === 'single_choice'" class="choice-list">
      <label v-for="opt in question.options" :key="opt" class="choice-row">
        <input
          type="radio"
          :name="`q-${question.id}`"
          :value="opt"
          :checked="chosen[0] === opt"
          @change="emit('update', { answer_choices: [opt] })"
        />
        <span>{{ opt }}</span>
      </label>
    </div>

    <div v-else-if="question.kind === 'multi_choice'" class="choice-list">
      <label v-for="opt in question.options" :key="opt" class="choice-row">
        <input
          type="checkbox"
          :checked="chosen.includes(opt)"
          @change="(e) => toggleMulti(opt, (e.target as HTMLInputElement).checked)"
        />
        <span>{{ opt }}</span>
      </label>
    </div>
  </div>
</template>

<style scoped>
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
.number-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.number-input {
  max-width: 8rem;
}
.unit {
  font-size: 0.9375rem;
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
