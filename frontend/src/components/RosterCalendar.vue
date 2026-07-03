<script setup lang="ts">
/**
 * A read-only month grid (Monday-first) for one chore's roster: each
 * occurrence day shows the assigned pseudonym(s), or a red "open" marker,
 * stacked for ``people_per_shift`` > 1. Days beyond the commit horizon are
 * ``tentative`` (faded + dashed); ``changed`` days (fold-in preview) get a
 * red ring. Non-occurrence days render as plain greyed numbers.
 */
import { computed } from "vue";
import type { CalendarDay } from "@/api/types";

const props = defineProps<{
  year: number;
  month: number; // 0-indexed
  days: CalendarDay[];
  locale: string;
  openLabel: string;
  anonLabel: string;
}>();

const byIso = computed(() => new Map(props.days.map((d) => [d.on_date, d])));

// Monday-first weekday initials, localised (2024-01-01 is a Monday).
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale, { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});

interface Cell {
  day: number | null;
  data: CalendarDay | null;
}
const cells = computed<Cell[]>(() => {
  const lead = (new Date(props.year, props.month, 1).getDay() + 6) % 7; // Mon = 0
  const daysInMonth = new Date(props.year, props.month + 1, 0).getDate();
  const out: Cell[] = Array.from({ length: lead }, () => ({ day: null, data: null }));
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${props.year}-${String(props.month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    out.push({ day: d, data: byIso.value.get(iso) ?? null });
  }
  return out;
});
</script>

<template>
  <div class="rc">
    <div class="rc-dow">
      <span v-for="(w, i) in weekdays" :key="`h${i}`">{{ w }}</span>
    </div>
    <div class="rc-grid">
      <div
        v-for="(c, i) in cells"
        :key="i"
        class="rc-cell"
        :class="{ occ: c.data, tentative: c.data?.tentative, changed: c.data?.changed }"
      >
        <span v-if="c.day" class="rc-num">{{ c.day }}</span>
        <ul v-if="c.data" class="rc-names">
          <li
            v-for="(a, j) in c.data.assignees"
            :key="j"
            :class="{ open: a.open, done: a.status === 'done', missed: a.status === 'missed' }"
          >
            {{ a.open ? openLabel : a.name || anonLabel }}
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rc {
  width: 100%;
}
.rc-dow,
.rc-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
}
.rc-dow span {
  text-align: center;
  font-size: 0.6875rem;
  color: var(--brand-text-muted);
  padding-bottom: 0.25rem;
  text-transform: capitalize;
}
.rc-cell {
  min-height: 2.75rem;
  border-radius: 6px;
  padding: 2px 3px;
  font-size: 0.875rem;
  color: var(--brand-text-muted);
}
/* An occurrence day: bordered card with the day number + assignee list. */
.rc-cell.occ {
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
}
.rc-cell.tentative {
  border-style: dashed;
  opacity: 0.7;
}
.rc-cell.changed {
  outline: 2px solid var(--brand-red);
  outline-offset: 1px;
}
.rc-num {
  display: block;
  font-size: 0.6875rem;
  color: var(--brand-text-muted);
  line-height: 1.1;
}
.rc-names {
  list-style: none;
  margin: 1px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.rc-names li {
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.15;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rc-names li.open {
  color: var(--brand-red);
}
.rc-names li.done {
  color: var(--brand-green);
}
.rc-names li.missed {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
</style>
