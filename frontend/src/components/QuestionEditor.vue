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
  | "multi_choice";

export interface QuestionDraft {
  id: string | null;
  kind: QuestionKind;
  prompt: string;
  required: boolean;
  options: string[];
  low_label: string | null;
  high_label: string | null;
}

const props = defineProps<{
  modelValue: QuestionDraft;
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
  (["rating", "short_text", "text", "single_choice", "multi_choice"] as QuestionKind[]).map(
    (k) => ({ value: k, label: t(`forms.question.kind.${k}`) }),
  ),
);

const isChoice = computed(
  () =>
    props.modelValue.kind === "single_choice" ||
    props.modelValue.kind === "multi_choice",
);
const isRating = computed(() => props.modelValue.kind === "rating");

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
  }
  emit("update:modelValue", next);
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

    <label class="required-row">
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

    <div v-if="isChoice" class="options-block">
      <p class="muted options-label">{{ t("forms.question.options") }}</p>
      <EditableList
        :items="modelValue.options"
        :item-label="(s: string) => s"
        :item-key="(s: string) => s"
        @remove="removeOption"
      >
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
</style>
