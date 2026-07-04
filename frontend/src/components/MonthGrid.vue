<script setup lang="ts">
/**
 * The shared monthly-calendar shell used by every calendar in the app
 * (admin roster + fold-in preview, public personal page, datepoll date
 * overview). Owns everything that must look identical: the ‹ month ›
 * navigator, Monday-first weekday header, a fixed six-week grid (so height
 * doesn't jump between months), the day number, and the "today" marker.
 *
 * Callers style each day via ``dayClass(iso)`` (e.g. occurrence / tentative
 * / changed) and fill its body through the ``#day`` scoped slot. Set
 * ``clickable(iso)`` to make a day a full-cell button that emits
 * ``day-click`` (the body slot then renders any anchored popover). No admin
 * deps — safe to import from the public mini-apps.
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    month: string; // YYYY-MM
    locale: string;
    weekdays: readonly string[];
    prevLabel?: string;
    nextLabel?: string;
    // Show the ‹ month › navigator. Off for stacked-months views (datepoll
    // voting) that render one grid per month with a plain title instead.
    // Default true — Vue would otherwise coerce an absent boolean to false.
    nav?: boolean;
    dayClass?: (iso: string) => Record<string, boolean> | undefined;
    clickable?: (iso: string) => boolean;
    // The day whose slot currently renders an open popover: it's lifted into
    // its own stacking context above sibling cells so the popover (and its
    // buttons) reliably sit on top and receive hover/clicks.
    activeIso?: string | null;
  }>(),
  { nav: true },
);
const emit = defineEmits<{ "update:month": [value: string]; "day-click": [iso: string] }>();

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const todayIso = isoOf(new Date());

const year = computed(() => Number(props.month.split("-")[0]));
const monthIdx = computed(() => Number(props.month.split("-")[1]) - 1);
const intlLocale = computed(() => (props.locale === "en" ? "en-GB" : props.locale === "nl" ? "nl-NL" : props.locale));
const monthLabel = computed(() =>
  new Date(year.value, monthIdx.value, 1).toLocaleDateString(intlLocale.value, { month: "long", year: "numeric" }),
);
function shift(delta: number) {
  const d = new Date(year.value, monthIdx.value + delta, 1);
  emit("update:month", `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
}

interface Cell {
  day: number | null;
  iso: string | null;
  today: boolean;
}
const cells = computed<Cell[]>(() => {
  const lead = (new Date(year.value, monthIdx.value, 1).getDay() + 6) % 7; // Mon = 0
  const dim = new Date(year.value, monthIdx.value + 1, 0).getDate();
  const out: Cell[] = Array.from({ length: lead }, () => ({ day: null, iso: null, today: false }));
  for (let d = 1; d <= dim; d++) {
    const iso = `${year.value}-${String(monthIdx.value + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    out.push({ day: d, iso, today: iso === todayIso });
  }
  while (out.length < 42) out.push({ day: null, iso: null, today: false }); // always six weeks
  return out;
});

function isClickable(c: Cell): boolean {
  return !!(c.iso && props.clickable?.(c.iso));
}
function onCellClick(c: Cell) {
  // The popover (rendered in the day slot) stops its own clicks, so this
  // only fires for a bare tap on the day cell.
  if (c.iso && props.clickable?.(c.iso)) emit("day-click", c.iso);
}
</script>

<template>
  <div class="mg">
    <div v-if="nav !== false" class="mg-nav">
      <button type="button" class="mg-navbtn" :aria-label="prevLabel" @click="shift(-1)">‹</button>
      <span class="mg-month">{{ monthLabel }}</span>
      <button type="button" class="mg-navbtn" :aria-label="nextLabel" @click="shift(1)">›</button>
    </div>
    <p v-else class="mg-title">{{ monthLabel }}</p>
    <div class="mg-dow">
      <span v-for="(w, i) in weekdays" :key="`h${i}`">{{ w }}</span>
    </div>
    <div class="mg-grid">
      <div
        v-for="(c, i) in cells"
        :key="i"
        class="mg-cell"
        :class="[
          c.day && dayClass ? dayClass(c.iso!) : undefined,
          { today: c.today, clickable: c.day && isClickable(c), 'is-active': c.iso && c.iso === activeIso },
        ]"
        :role="c.day && isClickable(c) ? 'button' : undefined"
        :tabindex="c.day && isClickable(c) ? 0 : undefined"
        :aria-label="c.day && isClickable(c) ? String(c.day) : undefined"
        @click="onCellClick(c)"
        @keydown.enter.prevent="onCellClick(c)"
      >
        <template v-if="c.day">
          <span class="mg-num">{{ c.day }}</span>
          <div class="mg-body">
            <slot name="day" :iso="c.iso!" :day="c.day" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mg-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.mg-navbtn {
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  border-radius: 8px;
  width: 2rem;
  height: 2rem;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  color: var(--brand-text);
}
.mg-month {
  font-weight: 600;
  min-width: 9rem;
  text-align: center;
  text-transform: capitalize;
}
.mg-title {
  font-weight: 600;
  margin: 0 0 0.5rem;
  text-transform: capitalize;
}
.mg-dow,
.mg-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}
.mg-dow span {
  text-align: center;
  font-size: 0.6875rem;
  color: var(--brand-text-muted);
  padding-bottom: 0.25rem;
  text-transform: capitalize;
}
/* Every day cell: top-aligned content, a little breathing room, six weeks
 * of uniform rows. */
.mg-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-height: 3rem;
  border-radius: 6px;
  padding: 1px 4px 4px;
  font-size: 0.875rem;
  color: var(--brand-text-muted);
}
/* An "occurrence" day (caller opts in via dayClass): bordered card. */
.mg-cell.occ {
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
}
.mg-cell.tentative {
  border-style: dashed;
}
.mg-cell.changed {
  outline: 2px solid var(--brand-red);
  outline-offset: 1px;
}
/* The whole day cell is the click target (no overlay button). */
.mg-cell.clickable {
  cursor: pointer;
}
/* The day with an open popover sits above its siblings (and its popover with
 * it), so the popover reliably captures hover/clicks. */
.mg-cell.is-active {
  z-index: 5;
}
.mg-cell.clickable:hover {
  border-color: var(--brand-red);
}
.mg-cell.clickable:focus-visible {
  outline: 2px solid var(--brand-red);
  outline-offset: 1px;
}
.mg-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.15rem;
  height: 1.15rem;
  font-size: 0.6875rem;
  color: var(--brand-text-muted);
  line-height: 1;
}
/* Today: a muted, rounded-square marker on the day number. */
.mg-cell.today .mg-num {
  background: var(--brand-text-muted);
  color: #fff;
  border-radius: 5px;
  font-weight: 600;
}
/* Not a positioning context, so an absolute popover in a day slot anchors
 * to the cell (drops below it, not below the text). */
.mg-body {
  margin-top: 4px;
  width: 100%;
}
</style>
