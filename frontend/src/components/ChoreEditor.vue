<script setup lang="ts">
/**
 * Editor for one chore on a roster. Shape mirrors the backend's
 * ``ChoreIn`` exactly so a parent collecting an array ships them as
 * ``chores`` without a transform. ``id`` is null for newly-added rows;
 * existing chores carry their server uuid so the diff-apply matches.
 *
 * The recurrence is edited via ``CycleGridPicker``, driven by the
 * roster-level ``periodWeeks``. Per-row move/delete mirror
 * ``QuestionEditor`` so both sit on the same ``useOrderedList`` parent.
 */
import AppButton from "@/components/AppButton.vue";
import AppInput from "@/components/AppInput.vue";
import { useI18n } from "vue-i18n";
import CycleGridPicker from "@/components/CycleGridPicker.vue";
import EmojiPicker from "@/components/EmojiPicker.vue";
import NumberStepper from "@/components/NumberStepper.vue";

export interface ChoreDraft {
  id: string | null;
  name: string;
  description: string | null;
  cycle_slots: number[];
  people_per_shift: number;
  // Every chore always carries an emoji (seeded with DEFAULT_CHORE_EMOJI).
  emoji: string;
}

const props = defineProps<{
  modelValue: ChoreDraft;
  /** Roster cycle length; drives the number of week-rows in the grid. */
  periodWeeks: number;
  canMoveUp: boolean;
  canMoveDown: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: ChoreDraft): void;
  (e: "delete"): void;
  (e: "moveUp"): void;
  (e: "moveDown"): void;
}>();

const { t } = useI18n();

function patch<K extends keyof ChoreDraft>(key: K, value: ChoreDraft[K]): void {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
</script>

<template>
  <div class="chore-editor">
    <div class="header-row">
      <span class="emoji-slot">
        <EmojiPicker :model-value="modelValue.emoji" @select="(e) => patch('emoji', e)" />
      </span>
      <AppInput
        :model-value="modelValue.name"
        :placeholder="t('chore.edit.choreNamePlaceholder')"
        fluid
        @update:model-value="(v) => patch('name', v ?? '')"
      />
      <div class="header-actions">
        <AppButton
          type="button"
          icon="arrow-up"
          size="small"
          severity="secondary"
          text
          :disabled="!canMoveUp"
          :aria-label="t('chore.edit.moveUp')"
          @click="emit('moveUp')"
        />
        <AppButton
          type="button"
          icon="arrow-down"
          size="small"
          severity="secondary"
          text
          :disabled="!canMoveDown"
          :aria-label="t('chore.edit.moveDown')"
          @click="emit('moveDown')"
        />
        <AppButton
          type="button"
          icon="trash"
          size="small"
          severity="secondary"
          text
          :aria-label="t('chore.edit.deleteChore')"
          @click="emit('delete')"
        />
      </div>
    </div>

    <AppInput
      :model-value="modelValue.description ?? ''"
      :placeholder="t('chore.edit.choreDescriptionPlaceholder')"
      fluid
      @update:model-value="(v) => patch('description', v ? v : null)"
    />

    <CycleGridPicker
      :model-value="modelValue.cycle_slots"
      :period-weeks="periodWeeks"
      @update:model-value="(v) => patch('cycle_slots', v)"
    />

    <div class="people-row">
      <span class="field-label">{{ t("chore.edit.peoplePerShift") }}</span>
      <NumberStepper
        :model-value="modelValue.people_per_shift"
        :min="1"
        :max="20"
        :aria-label="t('chore.edit.peoplePerShift')"
        @update:model-value="(v) => patch('people_per_shift', v)"
      />
    </div>
  </div>
</template>

<style scoped>
.chore-editor {
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
.emoji-slot {
  display: inline-flex;
  align-items: center;
}
.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.125rem;
}
.people-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  align-self: flex-start;
}
</style>
