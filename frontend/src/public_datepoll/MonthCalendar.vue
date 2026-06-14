<script setup lang="ts">
import { computed } from "vue";
import type { Availability } from "./api";
import type { Locale } from "@/public_shared/strings";

/** One full-width month grid. Candidate days carry their slots inline:
 *  a whole-day day is one tappable tri-state cell (the day itself); a
 *  day with time-slots shows the day number and a stacked pill per
 *  slot, each its own tri-state toggle. Non-candidate days render
 *  greyed and inert. ``answers[slotId]`` is the current state (``null``
 *  = unset). Emits ``toggle`` with the slot id; the parent owns the
 *  cycle. */

interface SlotCell {
  id: string;
  /** ``null`` = whole-day; otherwise the compact time label. */
  label: string | null;
}

const props = defineProps<{
  year: number;
  month: number; // 0-based
  slotsByIso: Record<string, SlotCell[]>;
  answers: Record<string, Availability | null>;
  locale: Locale;
}>();

const emit = defineEmits<{ toggle: [slotId: string] }>();

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

// Monday-first weekday headers, localised. 2024-01-01 is a Monday.
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});

interface Cell {
  day: number | null;
  iso: string | null;
  slots: SlotCell[];
  wholeDay: SlotCell | null;
}

const grid = computed<Cell[]>(() => {
  const first = new Date(props.year, props.month, 1);
  const lead = (first.getDay() + 6) % 7; // Monday-based leading blanks
  const daysInMonth = new Date(props.year, props.month + 1, 0).getDate();
  const out: Cell[] = [];
  for (let i = 0; i < lead; i++) out.push({ day: null, iso: null, slots: [], wholeDay: null });
  for (let d = 1; d <= daysInMonth; d++) {
    const key = iso(d);
    const slots = props.slotsByIso[key] ?? [];
    const wholeDay = slots.length === 1 && slots[0].label === null ? slots[0] : null;
    out.push({ day: d, iso: key, slots, wholeDay });
  }
  // Pad the final week with trailing blanks so the grid is a clean
  // rectangle (complete the last row only — no fixed 6-row height,
  // since months stack vertically rather than swap in place).
  while (out.length % 7 !== 0) out.push({ day: null, iso: null, slots: [], wholeDay: null });
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
        <span v-if="c.day === null" class="cell blank" />

        <!-- Non-candidate day. -->
        <span v-else-if="c.slots.length === 0" class="cell inert">{{ c.day }}</span>

        <!-- Whole-day candidate: the cell itself is the toggle. -->
        <button
          v-else-if="c.wholeDay"
          type="button"
          class="cell wholeday"
          :class="answers[c.wholeDay.id] ?? 'unset'"
          @click="emit('toggle', c.wholeDay.id)"
        >
          <span class="num">{{ c.day }}</span>
          <span v-if="answers[c.wholeDay.id]" class="glyph">{{ GLYPH[answers[c.wholeDay.id] as Availability] }}</span>
        </button>

        <!-- Timed candidate: day number + a tri-state pill per slot. -->
        <div v-else class="cell timed">
          <span class="num">{{ c.day }}</span>
          <button
            v-for="s in c.slots"
            :key="s.id"
            type="button"
            class="pill"
            :class="answers[s.id] ?? 'unset'"
            @click="emit('toggle', s.id)"
          >
            <span class="pill-label">{{ s.label }}</span>
            <span v-if="answers[s.id]" class="pill-glyph">{{ GLYPH[answers[s.id] as Availability] }}</span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.month { margin-bottom: 1.25rem; }
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
.cell {
  min-height: 3rem;
  border-radius: 8px;
  font-size: 0.875rem;
}
.blank { min-height: 0; }
.inert {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 0.25rem 0.375rem;
  color: var(--brand-border);
}

/* Whole-day cell — a single tri-state button filling the cell. */
.wholeday {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.125rem;
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
  cursor: pointer;
  font-weight: 600;
  transition: transform 80ms ease;
}
.wholeday:hover { transform: scale(1.04); }
.wholeday.unset { border-style: dashed; }
.glyph { font-size: 0.75rem; line-height: 1; }

/* Timed cell — day number top-right, a pill per slot stacked below. */
.timed {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 2px;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
}
.timed .num {
  align-self: flex-end;
  font-size: 0.6875rem;
  color: var(--brand-text-muted);
  line-height: 1;
  padding: 0 0.125rem;
}
.pill {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.125rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-bg);
  color: var(--brand-text);
  cursor: pointer;
  padding: 0.1875rem 0.125rem;
  font-size: 0.625rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.pill.unset { border-style: dashed; }
.pill-label { white-space: nowrap; }
.pill-glyph { font-size: 0.625rem; line-height: 1; }

/* Shared state colours (whole-day cell + timed pill). */
.wholeday.yes, .pill.yes { background: #1f7a3c; color: #fff; border-color: #1f7a3c; }
.wholeday.maybe, .pill.maybe { background: #c98a00; color: #fff; border-color: #c98a00; }
.wholeday.no, .pill.no { background: #6b6b6b; color: #fff; border-color: #6b6b6b; }
</style>
