<script setup lang="ts">
/**
 * A datepoll's proposed days as a calendar, built on the shared
 * ``MonthGrid`` (so it matches the roster calendars). Candidate days render
 * as occurrence cells showing their time range(s); whole-day slots show the
 * day alone. Read-only, month-navigable.
 */
import { computed } from "vue";
import MonthGrid from "./MonthGrid.vue";

interface Slot {
  on_date: string;
  start_time?: string | null;
  end_time?: string | null;
}

const props = defineProps<{
  month: string; // YYYY-MM
  slots: Slot[];
  locale: string;
  prevLabel: string;
  nextLabel: string;
}>();
const emit = defineEmits<{ "update:month": [value: string] }>();

const byIso = computed(() => {
  const m = new Map<string, string[]>();
  for (const s of props.slots) {
    if (!m.has(s.on_date)) m.set(s.on_date, []);
    if (s.start_time && s.end_time) m.get(s.on_date)!.push(`${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}`);
  }
  return m;
});
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
function dayClass(iso: string) {
  return { occ: byIso.value.has(iso) };
}
</script>

<template>
  <MonthGrid
    :month="month"
    :locale="locale"
    :weekdays="weekdays"
    :prev-label="prevLabel"
    :next-label="nextLabel"
    :day-class="dayClass"
    @update:month="(m: string) => emit('update:month', m)"
  >
    <template #day="{ iso }">
      <ul v-if="byIso.get(iso)?.length" class="mc-times">
        <li v-for="(t, j) in byIso.get(iso)" :key="j">{{ t }}</li>
      </ul>
    </template>
  </MonthGrid>
</template>

<style scoped>
.mc-times {
  list-style: none;
  margin: 0;
  padding: 0;
}
.mc-times li {
  font-size: 0.6875rem;
  font-weight: 600;
  line-height: 1.25;
}
</style>
