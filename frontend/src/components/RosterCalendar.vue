<script setup lang="ts">
/**
 * One chore's roster month, built on the shared ``MonthGrid``: each
 * occurrence day lists its assignees (comma-separated, wrapping) or a red
 * "open" marker; tentative days are dashed, changed days (fold-in preview)
 * ringed. View-only.
 */
import { computed } from "vue";
import MonthGrid from "./MonthGrid.vue";
import type { CalendarDay } from "@/api/types";

const props = defineProps<{
  month: string; // YYYY-MM
  days: CalendarDay[];
  locale: string;
  openLabel: string;
  anonLabel: string;
  prevLabel: string;
  nextLabel: string;
}>();
const emit = defineEmits<{ "update:month": [value: string] }>();

const byIso = computed(() => new Map(props.days.map((d) => [d.on_date, d])));
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
function dayClass(iso: string) {
  const d = byIso.value.get(iso);
  return { occ: !!d, tentative: !!d?.tentative, changed: !!d?.changed };
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
      <ul v-if="byIso.get(iso)" class="rc-names">
        <li
          v-for="(a, j) in byIso.get(iso)!.assignees"
          :key="j"
          :class="{ open: a.open, done: a.status === 'done', missed: a.status === 'missed' }"
        >
          <span v-if="a.status === 'done'" class="rc-check" aria-hidden="true">✓ </span>{{
            a.open ? openLabel : a.name || anonLabel
          }}
        </li>
      </ul>
    </template>
  </MonthGrid>
</template>

<style scoped>
/* Assignees as a comma-separated, wrapping list. */
.rc-names {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rc-names li {
  display: inline;
  font-size: 0.75rem;
  line-height: 1.3;
}
.rc-names li:not(:last-child)::after {
  content: ", ";
  color: var(--brand-text-muted);
}
.rc-names li.open {
  color: var(--brand-red);
}
.rc-names li.done {
  color: var(--brand-text-muted);
}
.rc-names li.missed {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
.rc-check {
  color: var(--brand-green);
}
</style>
