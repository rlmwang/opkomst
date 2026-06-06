<script setup lang="ts">
import Textarea from "primevue/textarea";
import InputText from "primevue/inputtext";
import { computed } from "vue";
import RatingScale from "@/components/RatingScale.vue";

/**
 * Public-side input for one form question. Switches on
 * ``question.kind`` and emits the answer in the shape the backend
 * submit handler expects, keyed by the field that's meaningful
 * for the kind:
 *
 *   rating        → { answer_int: 1..5 | null }
 *   text          → { answer_text: string }
 *   short_text    → { answer_text: string }
 *   single_choice → { answer_choices: [option] | [] }
 *   multi_choice  → { answer_choices: option[] }
 *
 * The parent (PublicFormPage) collects answers keyed by question
 * id and ships them as one ``answers`` array.
 */
export interface PublicQuestion {
  id: string;
  kind: string;
  prompt: string;
  required: boolean;
  options?: string[];
  low_label?: string | null;
  high_label?: string | null;
}

export type Answer = {
  answer_int?: number | null;
  answer_text?: string;
  answer_choices?: string[];
};

const props = defineProps<{
  question: PublicQuestion;
  modelValue: Answer;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: Answer): void;
}>();

const options = computed<string[]>(() => props.question.options ?? []);

function setRating(value: number | null) {
  emit("update:modelValue", { answer_int: value });
}

function setText(value: string) {
  emit("update:modelValue", { answer_text: value });
}

function setSingle(value: string) {
  emit("update:modelValue", { answer_choices: value ? [value] : [] });
}

function toggleMulti(option: string, checked: boolean) {
  const current = props.modelValue.answer_choices ?? [];
  const next = checked
    ? [...current.filter((c) => c !== option), option]
    : current.filter((c) => c !== option);
  emit("update:modelValue", { answer_choices: next });
}

function isChecked(option: string): boolean {
  return (props.modelValue.answer_choices ?? []).includes(option);
}
</script>

<template>
  <div class="question-input">
    <label class="prompt">
      {{ question.prompt }}
      <span v-if="question.required" class="required-mark" aria-hidden="true">*</span>
    </label>

    <RatingScale
      v-if="question.kind === 'rating'"
      :model-value="modelValue.answer_int ?? null"
      :label-low="question.low_label ?? ''"
      :label-high="question.high_label ?? ''"
      @update:model-value="setRating"
    />

    <Textarea
      v-else-if="question.kind === 'text'"
      :model-value="modelValue.answer_text ?? ''"
      :maxlength="2000"
      rows="3"
      auto-resize
      fluid
      @update:model-value="(v: string) => setText(v ?? '')"
    />

    <InputText
      v-else-if="question.kind === 'short_text'"
      :model-value="modelValue.answer_text ?? ''"
      :maxlength="200"
      fluid
      @update:model-value="(v: string | undefined) => setText(v ?? '')"
    />

    <div v-else-if="question.kind === 'single_choice'" class="choice-list">
      <label v-for="opt in options" :key="opt" class="choice-row">
        <input
          type="radio"
          :name="`q-${question.id}`"
          :value="opt"
          :checked="(modelValue.answer_choices ?? [])[0] === opt"
          @change="setSingle(opt)"
        />
        <span>{{ opt }}</span>
      </label>
    </div>

    <div v-else-if="question.kind === 'multi_choice'" class="choice-list">
      <label v-for="opt in options" :key="opt" class="choice-row">
        <input
          type="checkbox"
          :checked="isChecked(opt)"
          @change="(ev) => toggleMulti(opt, (ev.target as HTMLInputElement).checked)"
        />
        <span>{{ opt }}</span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.question-input {
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
