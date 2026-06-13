<script setup lang="ts">
import { computed } from "vue";
import type { Availability } from "./api";
import type { Locale } from "@/public_shared/strings";

/** One month grid. Candidate days (those present as keys in
 *  ``cells``) are tappable tri-state cells; every other day renders
 *  greyed and inert. ``cells[iso]`` is the current state (``null`` =
 *  unset). Emits ``toggle`` with the ISO date when a candidate day is
 *  tapped; the parent owns the cycle. */
const props = defineProps<{
  year: number;
  month: number; // 0-based
  cells: Record<string, Availability | null>;
  locale: Locale;
}>();

const emit = defineEmits<{ toggle: [iso: string] }>();

const GLYPH: Record<Availability, string> = { yes: "✓", maybe: "~", no: "✕" };

function iso(day: number): string {
  return `${props.year}-${String(props.month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

const monthLabel = computed(() =>
  new Date(props.year, props.month, 1).toLocaleDateString(props.locale === "en" ? "en-GB" : "nl-NL", {
    month: "long",
    year: "numeric",
  }),
);

// Monday-first weekday headers, localised.
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  // 2024-01-01 is a Monday.
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});

interface Cell {
  day: number | null;
  iso: string | null;
  state: Availability | null;
  candidate: boolean;
}

const grid = computed<Cell[]>(() => {
  const first = new Date(props.year, props.month, 1);
  const lead = (first.getDay() + 6) % 7; // Monday-based leading blanks
  const daysInMonth = new Date(props.year, props.month + 1, 0).getDate();
  const out: Cell[] = [];
  for (let i = 0; i < lead; i++) out.push({ day: null, iso: null, state: null, candidate: false });
  for (let d = 1; d <= daysInMonth; d++) {
    const key = iso(d);
    const candidate = key in props.cells;
    out.push({ day: d, iso: key, state: candidate ? props.cells[key] : null, candidate });
  }
  // Pad with trailing blanks to a constant 6 rows (42 cells) so a
  // 5-row month is the same height as a 6-row one — otherwise the
  // page jumps as months of different lengths sit next to / below
  // each other.
  while (out.length < 42) out.push({ day: null, iso: null, state: null, candidate: false });
  return out;
});
</script>

<template>
  <div class="month">
    <p class="month-label">{{ monthLabel }}</p>
    <div class="weekdays">
      <span v-for="w in weekdays" :key="w">{{ w }}</span>
    </div>
    <div class="days">
      <template v-for="(c, i) in grid" :key="i">
        <span v-if="c.day === null" class="blank" />
        <button
          v-else-if="c.candidate"
          type="button"
          class="day candidate"
          :class="c.state ?? 'unset'"
          @click="emit('toggle', c.iso as string)"
        >
          <span class="num">{{ c.day }}</span>
          <span v-if="c.state" class="glyph">{{ GLYPH[c.state] }}</span>
        </button>
        <span v-else class="day inert">{{ c.day }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.month { margin-bottom: 1rem; }
.month-label { margin: 0 0 0.5rem; font-weight: 600; text-transform: capitalize; }
.weekdays, .days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}
.weekdays span {
  text-align: center;
  font-size: 0.75rem;
  color: var(--brand-text-muted);
  padding-bottom: 0.25rem;
  text-transform: capitalize;
}
.blank { aspect-ratio: 1; }
.day {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 0.875rem;
}
.day.inert { color: var(--brand-border); }
.day.candidate {
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
  cursor: pointer;
  font-weight: 600;
  transition: transform 80ms ease;
}
.day.candidate:hover { transform: scale(1.05); }
.day.candidate.unset { border-style: dashed; }
.day.candidate.yes { background: #1f7a3c; color: #fff; border-color: #1f7a3c; }
.day.candidate.maybe { background: #c98a00; color: #fff; border-color: #c98a00; }
.day.candidate.no { background: #6b6b6b; color: #fff; border-color: #6b6b6b; }
.glyph { font-size: 0.75rem; line-height: 1; }
</style>
