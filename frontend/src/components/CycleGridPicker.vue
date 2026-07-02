<script setup lang="ts">
/**
 * Recurrence selector for one chore. Renders ``periodWeeks`` rows of
 * seven day-toggles (Mon..Sun). Each toggle maps to a flat offset into
 * the roster's k-week cycle: ``offset = week * 7 + day`` (Mon=0). For
 * k=1 it's a single weekday row, degrading to a plain weekday picker.
 *
 * v-model is the chore's ``cycle_slots`` (a sorted ``number[]`` of
 * offsets). Kept in lock-step with the roster-level ``period_weeks`` —
 * the parent clamps out-of-range offsets when k shrinks (task 04 page).
 */
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  modelValue: number[];
  periodWeeks: number;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: number[]): void;
}>();

const { t } = useI18n();

const dayLabels = computed(() => [
  t("chores.edit.weekday.mon"),
  t("chores.edit.weekday.tue"),
  t("chores.edit.weekday.wed"),
  t("chores.edit.weekday.thu"),
  t("chores.edit.weekday.fri"),
  t("chores.edit.weekday.sat"),
  t("chores.edit.weekday.sun"),
]);

const weeks = computed(() => Math.max(1, props.periodWeeks));

function offset(week: number, day: number): number {
  return week * 7 + day;
}

function isSet(week: number, day: number): boolean {
  return props.modelValue.includes(offset(week, day));
}

function toggle(week: number, day: number): void {
  const o = offset(week, day);
  const set = new Set(props.modelValue);
  if (set.has(o)) set.delete(o);
  else set.add(o);
  emit(
    "update:modelValue",
    [...set].sort((a, b) => a - b),
  );
}
</script>

<template>
  <div class="cycle-grid">
    <div v-for="week in weeks" :key="week" class="cycle-week">
      <div class="day-row">
        <button
          v-for="(label, day) in dayLabels"
          :key="day"
          type="button"
          class="day-toggle"
          :class="{ active: isSet(week - 1, day) }"
          :aria-pressed="isSet(week - 1, day)"
          @click="toggle(week - 1, day)"
        >
          {{ label }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cycle-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.cycle-week {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.day-row {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}
.day-toggle {
  flex: 1 1 0;
  min-width: 2.75rem;
  padding: 0.4rem 0.25rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.day-toggle:hover {
  border-color: var(--brand-red);
}
.day-toggle.active {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #ffffff;
  font-weight: 600;
}
</style>
