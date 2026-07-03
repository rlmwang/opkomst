<script setup lang="ts">
/**
 * A read-only month grid (Monday-first) that highlights a set of dates —
 * used to preview a datepoll's proposed days as a calendar. Purely
 * presentational: the caller passes the month and the ISO dates to mark.
 */
import { computed } from "vue";

const props = defineProps<{
  year: number;
  month: number; // 0-indexed (0 = January)
  highlighted: string[]; // ISO yyyy-mm-dd
  locale: string;
}>();

const marked = computed(() => new Set(props.highlighted));

const title = computed(() =>
  new Intl.DateTimeFormat(props.locale, { month: "long", year: "numeric" }).format(new Date(props.year, props.month, 1)),
);

// Weekday initials, Monday-first, in the active locale (2024-01-01 = Monday).
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale, { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});

interface Cell {
  day: number;
  marked: boolean;
}
const cells = computed<(Cell | null)[]>(() => {
  const lead = (new Date(props.year, props.month, 1).getDay() + 6) % 7; // Mon = 0
  const daysInMonth = new Date(props.year, props.month + 1, 0).getDate();
  const out: (Cell | null)[] = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${props.year}-${String(props.month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    out.push({ day: d, marked: marked.value.has(iso) });
  }
  return out;
});
</script>

<template>
  <div class="month-cal">
    <div class="month-title">{{ title }}</div>
    <div class="month-grid">
      <span v-for="(w, i) in weekdays" :key="`h${i}`" class="dow">{{ w }}</span>
      <span v-for="(c, i) in cells" :key="i" class="day" :class="{ blank: !c, marked: c?.marked }">{{ c?.day ?? "" }}</span>
    </div>
  </div>
</template>

<style scoped>
.month-cal {
  width: 17rem;
  max-width: 100%;
}
.month-title {
  font-weight: 600;
  margin-bottom: 0.5rem;
  text-transform: capitalize;
}
.month-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
}
.dow {
  text-align: center;
  font-size: 0.6875rem;
  color: var(--brand-text-muted);
  padding-bottom: 0.125rem;
}
.day {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.875rem;
  border-radius: 6px;
}
.day.marked {
  background: var(--brand-red);
  color: #fff;
  font-weight: 600;
}
.day.blank {
  visibility: hidden;
}
</style>
