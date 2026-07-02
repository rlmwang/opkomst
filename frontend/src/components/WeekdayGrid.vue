<script setup lang="ts">
/**
 * Read-only weekday grid — the display twin of ``CycleGridPicker``.
 * Renders ``periodWeeks`` rows of seven day cells (Mon..Sun), the active
 * ones (in ``cycleSlots``, offset = week*7 + day) highlighted. Pure and
 * dependency-free (labels are passed in), so both the admin details page
 * and the public mini-app can use it without pulling in i18n/PrimeVue.
 */
import { computed } from "vue";

const props = defineProps<{
  cycleSlots: number[];
  periodWeeks: number;
  /** Seven weekday labels, Mon..Sun. */
  weekdayLabels: readonly string[];
}>();

const weeks = computed(() => Math.max(1, props.periodWeeks));

function isSet(week: number, day: number): boolean {
  return props.cycleSlots.includes(week * 7 + day);
}
</script>

<template>
  <div class="weekday-grid">
    <div v-for="week in weeks" :key="week" class="wg-row">
      <span
        v-for="(label, day) in weekdayLabels"
        :key="day"
        class="wg-day"
        :class="{ active: isSet(week - 1, day) }"
      >{{ label }}</span>
    </div>
  </div>
</template>

<style scoped>
.weekday-grid {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.wg-row {
  display: flex;
  gap: 0.25rem;
}
.wg-day {
  flex: 1 1 0;
  min-width: 2rem;
  text-align: center;
  padding: 0.25rem 0.2rem;
  border: 1px solid var(--brand-border);
  border-radius: 5px;
  font-size: 0.75rem;
  color: var(--brand-text-muted);
  background: var(--brand-surface);
}
.wg-day.active {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #ffffff;
  font-weight: 600;
}
</style>
