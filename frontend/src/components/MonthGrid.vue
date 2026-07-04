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

const props = defineProps<{
  month: string; // YYYY-MM
  locale: string;
  weekdays: readonly string[];
  prevLabel: string;
  nextLabel: string;
  dayClass?: (iso: string) => Record<string, boolean> | undefined;
  clickable?: (iso: string) => boolean;
}>();
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
</script>

<template>
  <div class="mg">
    <div class="mg-nav">
      <button type="button" class="mg-navbtn" :aria-label="prevLabel" @click="shift(-1)">‹</button>
      <span class="mg-month">{{ monthLabel }}</span>
      <button type="button" class="mg-navbtn" :aria-label="nextLabel" @click="shift(1)">›</button>
    </div>
    <div class="mg-dow">
      <span v-for="(w, i) in weekdays" :key="`h${i}`">{{ w }}</span>
    </div>
    <div class="mg-grid">
      <div
        v-for="(c, i) in cells"
        :key="i"
        class="mg-cell"
        :class="[c.day && dayClass ? dayClass(c.iso!) : undefined, { today: c.today, clickable: c.day && clickable && clickable(c.iso!) }]"
      >
        <template v-if="c.day">
          <button
            v-if="clickable && clickable(c.iso!)"
            type="button"
            class="mg-daybtn"
            :aria-label="String(c.day)"
            @click.stop="emit('day-click', c.iso!)"
          />
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
.mg-cell.clickable {
  cursor: pointer;
}
/* Full-cell click target sitting above the (transparent) body so the whole
 * day card is tappable; the body/popover paint over it and stop clicks. */
.mg-daybtn {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  border-radius: 6px;
}
.mg-cell.clickable:hover .mg-daybtn {
  background: color-mix(in srgb, var(--brand-red) 5%, transparent);
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
/* The body sits above the full-cell button but lets clicks fall through to
 * it (so tapping a name still triggers the day). Interactive bits inside
 * (popovers) re-enable pointer events themselves. */
.mg-body {
  position: relative;
  z-index: 2;
  margin-top: 4px;
  width: 100%;
  pointer-events: none;
}
</style>
