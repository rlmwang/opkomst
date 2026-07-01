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
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import { useI18n } from "vue-i18n";
import CycleGridPicker from "@/components/CycleGridPicker.vue";
import EmojiPicker from "@/components/EmojiPicker.vue";

export interface ChoreDraft {
  id: string | null;
  name: string;
  description: string | null;
  cycle_slots: number[];
  people_per_shift: number;
  emoji: string | null;
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
        <button
          v-if="modelValue.emoji"
          type="button"
          class="emoji-clear"
          :aria-label="t('chores.edit.clearEmoji')"
          v-tooltip.top="t('chores.edit.clearEmoji')"
          @click="patch('emoji', null)"
        >{{ modelValue.emoji }}</button>
        <EmojiPicker v-else @select="(e) => patch('emoji', e)" />
      </span>
      <InputText
        :model-value="modelValue.name"
        :placeholder="t('chores.edit.choreNamePlaceholder')"
        fluid
        @update:model-value="(v) => patch('name', v ?? '')"
      />
      <div class="header-actions">
        <Button
          type="button"
          icon="pi pi-arrow-up"
          size="small"
          severity="secondary"
          text
          :disabled="!canMoveUp"
          :aria-label="t('chores.edit.moveUp')"
          @click="emit('moveUp')"
        />
        <Button
          type="button"
          icon="pi pi-arrow-down"
          size="small"
          severity="secondary"
          text
          :disabled="!canMoveDown"
          :aria-label="t('chores.edit.moveDown')"
          @click="emit('moveDown')"
        />
        <Button
          type="button"
          icon="pi pi-trash"
          size="small"
          severity="secondary"
          text
          :aria-label="t('chores.edit.deleteChore')"
          @click="emit('delete')"
        />
      </div>
    </div>

    <InputText
      :model-value="modelValue.description ?? ''"
      :placeholder="t('chores.edit.choreDescriptionPlaceholder')"
      fluid
      @update:model-value="(v) => patch('description', v ? v : null)"
    />

    <div class="days-block">
      <p class="muted days-label">{{ t("chores.edit.daysLabel") }}</p>
      <CycleGridPicker
        :model-value="modelValue.cycle_slots"
        :period-weeks="periodWeeks"
        @update:model-value="(v) => patch('cycle_slots', v)"
      />
    </div>

    <label class="people-row">
      <span>{{ t("chores.edit.peoplePerShift") }}</span>
      <InputNumber
        :model-value="modelValue.people_per_shift"
        :min="1"
        :max="20"
        show-buttons
        button-layout="horizontal"
        @update:model-value="(v) => patch('people_per_shift', v ?? 1)"
      />
    </label>
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
.emoji-clear {
  background: none;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 1.1rem;
  line-height: 1;
  padding: 0.3rem 0.4rem;
}
.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.125rem;
}
.days-block {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.days-label {
  margin: 0;
  font-size: 0.8125rem;
}
.people-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  align-self: flex-start;
}
</style>
