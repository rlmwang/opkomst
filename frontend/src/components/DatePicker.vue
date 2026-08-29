<script setup lang="ts">
/**
 * The app's date and time picker. Replaces PrimeVue's ``DatePicker``,
 * whose three chunks cost 81 kB gzipped and were the only PrimeVue on
 * the public chore page.
 *
 * The prop names are PrimeVue's, so a call site changes its import and
 * nothing else. Three shapes are supported, which is what the app uses:
 * a date input with a popup calendar, a time-only input with an hour and
 * minute spinner, and an inline calendar that selects several days.
 *
 * The geometry is Aura's, so the panel, the round 2rem day cells and the
 * input keep the proportions they had. The colours are the app's own
 * semantic tokens rather than the PrimeVue surface ramp: ``--brand-text``
 * over ``--brand-surface-700`` and ``--brand-border`` over
 * ``--brand-surface-200``, which is what ``MonthGrid`` and every
 * hand-rolled control already read. Surface and accent resolve to the
 * same values either way.
 *
 * The input keeps the form-field values, because on the two admin pages
 * it sits in a row of PrimeVue ``InputText`` fields and has to match
 * them.
 *
 * Month and weekday names come from ``Intl`` in the page language, the
 * way ``MonthGrid`` does. PrimeVue was configured with only
 * ``firstDayOfWeek``, so its default English locale showed through and
 * every picker in the app read "March" over "Mo Tu We" on a Dutch page.
 *
 * No admin dependencies: the public chore page imports this directly.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: Date | Date[] | null | undefined;
    /** Drives Intl for month and weekday names, and the button labels. */
    locale?: string;
    /** PrimeVue's format vocabulary: ``dd`` and ``mm`` zero-padded,
     *  ``yy`` the full four-digit year. */
    dateFormat?: string;
    placeholder?: string;
    fluid?: boolean;
    showButtonBar?: boolean;
    timeOnly?: boolean;
    hourFormat?: "12" | "24";
    stepMinute?: number;
    inline?: boolean;
    selectionMode?: "single" | "multiple";
    manualInput?: boolean;
    disabled?: boolean;
    ariaLabel?: string;
  }>(),
  {
    locale: "nl",
    dateFormat: "dd-mm-yy",
    hourFormat: "24",
    stepMinute: 1,
    selectionMode: "single",
    manualInput: true,
  },
);
const emit = defineEmits<{ "update:modelValue": [Date | Date[] | null] }>();

const LABELS: Record<string, Record<string, string>> = {
  nl: { today: "Vandaag", clear: "Wissen", prev: "Vorige maand", next: "Volgende maand", choose: "Kies een datum" },
  en: { today: "Today", clear: "Clear", prev: "Previous month", next: "Next month", choose: "Choose a date" },
};
const label = computed(() => LABELS[props.locale] ?? LABELS.nl);
const intlLocale = computed(() => (props.locale === "en" ? "en-GB" : "nl-NL"));

const root = ref<HTMLElement>();
const input = ref<HTMLInputElement>();
const panel = ref<HTMLElement>();
const open = ref(false);
const focused = ref(false);
const panelStyle = ref<Record<string, string>>({});

// --- value shape -----------------------------------------------------
// Single selection carries a Date; multiple carries an array. Everything
// below works off ``selected``, a list either way.
const selected = computed<Date[]>(() => {
  const v = props.modelValue;
  if (!v) return [];
  return Array.isArray(v) ? v.filter(Boolean) : [v];
});

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const selectedIsos = computed(() => new Set(selected.value.map(isoOf)));
const todayIso = isoOf(new Date());

// --- the month on show ----------------------------------------------
function monthKeyOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const viewMonth = ref(monthKeyOf(selected.value[0] ?? new Date()));
// Opening the panel lands on the selected date's month, not wherever it
// was left. A value arriving from the server after mount does the same.
watch(
  () => props.modelValue,
  () => {
    if (selected.value[0]) viewMonth.value = monthKeyOf(selected.value[0]);
  },
);

const viewYear = computed(() => Number(viewMonth.value.split("-")[0]));
const viewMonthIdx = computed(() => Number(viewMonth.value.split("-")[1]) - 1);

function shiftMonth(delta: number): void {
  const d = new Date(viewYear.value, viewMonthIdx.value + delta, 1);
  viewMonth.value = monthKeyOf(d);
}

const monthTitle = computed(() =>
  new Date(viewYear.value, viewMonthIdx.value, 1).toLocaleDateString(intlLocale.value, { month: "long" }),
);

const weekdayNames = computed(() => {
  // 2024-01-01 was a Monday, which is where the week starts here.
  const fmt = new Intl.DateTimeFormat(intlLocale.value, { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});

interface Cell {
  date: Date;
  iso: string;
  day: number;
  otherMonth: boolean;
}
// Six weeks, always, so the panel does not change height between months.
// Leading and trailing days from the neighbouring months are shown but
// not selectable, which is PrimeVue's showOtherMonths without
// selectOtherMonths.
const weeks = computed<Cell[][]>(() => {
  const first = new Date(viewYear.value, viewMonthIdx.value, 1);
  const lead = (first.getDay() + 6) % 7;
  const start = new Date(viewYear.value, viewMonthIdx.value, 1 - lead);
  const out: Cell[][] = [];
  for (let w = 0; w < 6; w++) {
    const row: Cell[] = [];
    for (let d = 0; d < 7; d++) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d);
      row.push({ date, iso: isoOf(date), day: date.getDate(), otherMonth: date.getMonth() !== viewMonthIdx.value });
    }
    out.push(row);
  }
  return out;
});

// --- formatting and parsing -----------------------------------------
/** PrimeVue's ``formatDate`` for the tokens this app uses. */
function formatDate(date: Date, format: string): string {
  let out = "";
  for (let i = 0; i < format.length; i++) {
    const c = format[i];
    const doubled = format[i + 1] === c;
    if (c === "d") {
      out += doubled ? String(date.getDate()).padStart(2, "0") : String(date.getDate());
      if (doubled) i++;
    } else if (c === "m") {
      out += doubled ? String(date.getMonth() + 1).padStart(2, "0") : String(date.getMonth() + 1);
      if (doubled) i++;
    } else if (c === "y") {
      // ``yy`` is the four-digit year, ``y`` the last two. PrimeVue
      // inherited that from jQuery UI and the call sites rely on it.
      out += doubled ? String(date.getFullYear()) : String(date.getFullYear() % 100).padStart(2, "0");
      if (doubled) i++;
    } else {
      out += c;
    }
  }
  return out;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function formatTime(date: Date): string {
  if (props.hourFormat === "12") {
    const h = date.getHours() % 12 || 12;
    return `${pad(h)}:${pad(date.getMinutes())} ${date.getHours() < 12 ? "AM" : "PM"}`;
  }
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const displayValue = computed(() => {
  if (props.timeOnly) return selected.value[0] ? formatTime(selected.value[0]) : "";
  return selected.value.map((d) => formatDate(d, props.dateFormat)).join(", ");
});

/** Read back what the format writes. Anything that does not parse to a
 *  real date leaves the model alone, so a half-typed day is not a
 *  deletion. */
function parseDate(text: string, format: string): Date | null {
  const order: string[] = [];
  for (let i = 0; i < format.length; i++) {
    const c = format[i];
    if (c === "d" || c === "m" || c === "y") {
      order.push(c);
      while (format[i + 1] === c) i++;
    }
  }
  const parts = text.split(/\D+/).filter(Boolean);
  if (parts.length !== order.length) return null;
  let day = 1;
  let month = 1;
  let year = new Date().getFullYear();
  order.forEach((token, i) => {
    const n = Number(parts[i]);
    if (token === "d") day = n;
    else if (token === "m") month = n;
    else year = parts[i].length <= 2 ? 2000 + n : n;
  });
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
}

function parseTime(text: string): Date | null {
  const m = /^(\d{1,2})[:.](\d{1,2})/.exec(text.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  const base = selected.value[0] ? new Date(selected.value[0]) : new Date();
  base.setHours(h, min, 0, 0);
  return base;
}

function onInputTyped(event: Event): void {
  const text = (event.target as HTMLInputElement).value;
  if (!text.trim()) {
    emit("update:modelValue", props.selectionMode === "multiple" ? [] : null);
    return;
  }
  const parsed = props.timeOnly ? parseTime(text) : parseDate(text, props.dateFormat);
  if (!parsed) return;
  if (!props.timeOnly) viewMonth.value = monthKeyOf(parsed);
  emit("update:modelValue", props.selectionMode === "multiple" ? [parsed] : parsed);
}

// The input shows the model, except while it is being typed into: a
// reformat mid-keystroke moves the caret.
const typedText = ref("");
const inputValue = computed(() => (focused.value ? typedText.value : displayValue.value));
watch(displayValue, (v) => {
  typedText.value = v;
});

// --- selection -------------------------------------------------------
function pick(cell: Cell): void {
  if (cell.otherMonth) return;
  if (props.selectionMode === "multiple") {
    const kept = selected.value.filter((d) => isoOf(d) !== cell.iso);
    emit("update:modelValue", kept.length === selected.value.length ? [...selected.value, cell.date] : kept);
    return;
  }
  // Keep the time a value already carried, so a picker bound to a
  // date-and-time value does not reset it to midnight.
  const next = new Date(cell.date);
  const prev = selected.value[0];
  if (prev) next.setHours(prev.getHours(), prev.getMinutes(), 0, 0);
  emit("update:modelValue", next);
  hide();
}

function stepTime(unit: "hour" | "minute", delta: number): void {
  const base = selected.value[0] ? new Date(selected.value[0]) : new Date(new Date().setSeconds(0, 0));
  if (unit === "hour") base.setHours((base.getHours() + delta + 24) % 24);
  else {
    const step = props.stepMinute || 1;
    const minutes = base.getMinutes() + delta * step;
    base.setMinutes(((minutes % 60) + 60) % 60);
  }
  base.setSeconds(0, 0);
  emit("update:modelValue", base);
}

const timeValue = computed(() => selected.value[0] ?? null);

function selectToday(): void {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  viewMonth.value = monthKeyOf(now);
  emit("update:modelValue", props.selectionMode === "multiple" ? [now] : now);
  hide();
}

function clearValue(): void {
  emit("update:modelValue", props.selectionMode === "multiple" ? [] : null);
  hide();
}

// --- the overlay -----------------------------------------------------
// Positioned against the viewport and teleported to the body, which is
// what PrimeVue's ``appendTo: "body"`` did: a panel inside the form
// would be clipped by any card that hides its overflow.
function place(): void {
  const anchor = root.value;
  const box = panel.value;
  if (!anchor || !box) return;
  const rect = anchor.getBoundingClientRect();
  const height = box.offsetHeight;
  const below = window.innerHeight - rect.bottom;
  const flip = below < height + 8 && rect.top > height + 8;
  panelStyle.value = {
    position: "absolute",
    insetInlineStart: `${rect.left + window.scrollX}px`,
    top: `${(flip ? rect.top - height : rect.bottom) + window.scrollY}px`,
    minWidth: `${rect.width}px`,
  };
}

function show(): void {
  if (props.disabled || open.value) return;
  if (selected.value[0]) viewMonth.value = monthKeyOf(selected.value[0]);
  open.value = true;
  requestAnimationFrame(place);
}

function hide(): void {
  open.value = false;
}

function onDocumentPointerDown(event: PointerEvent): void {
  if (!open.value) return;
  const target = event.target as Node;
  if (root.value?.contains(target) || panel.value?.contains(target)) return;
  hide();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && open.value) {
    hide();
    input.value?.focus();
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerDown, true);
  window.addEventListener("resize", place);
  window.addEventListener("scroll", place, true);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown, true);
  window.removeEventListener("resize", place);
  window.removeEventListener("scroll", place, true);
});
</script>

<template>
  <div ref="root" class="dp" :class="{ 'dp-fluid': fluid, 'dp-inline': inline }" @keydown="onKeydown">
    <input
      v-if="!inline"
      ref="input"
      type="text"
      class="dp-input"
      :value="inputValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :readonly="!manualInput"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      aria-haspopup="dialog"
      autocomplete="off"
      @focus="focused = true; show()"
      @blur="focused = false"
      @click="show"
      @input="
        typedText = ($event.target as HTMLInputElement).value;
        onInputTyped($event);
      "
    />

    <!-- Inline renders in place; the popup is teleported so no card can
         clip it. Both use the same panel markup. -->
    <Teleport to="body" :disabled="inline">
      <div
        v-if="inline || open"
        ref="panel"
        class="dp-panel"
        :class="{ 'dp-panel-inline': inline, 'dp-panel-timeonly': timeOnly }"
        :style="inline ? undefined : panelStyle"
        role="dialog"
        :aria-label="ariaLabel ?? label.choose"
      >
        <template v-if="!timeOnly">
          <div class="dp-header">
            <button type="button" class="dp-navbtn" :aria-label="label.prev" @click="shiftMonth(-1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <span class="dp-title">
              <span class="dp-title-month">{{ monthTitle }}</span>
              <span class="dp-title-year">{{ viewYear }}</span>
            </span>
            <button type="button" class="dp-navbtn" :aria-label="label.next" @click="shiftMonth(1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6" /></svg>
            </button>
          </div>

          <table class="dp-dayview">
            <thead>
              <tr>
                <th v-for="(w, i) in weekdayNames" :key="i" class="dp-weekday-cell" scope="col">
                  <span class="dp-weekday">{{ w }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(week, wi) in weeks" :key="wi">
                <td v-for="cell in week" :key="cell.iso" class="dp-day-cell" :class="{ 'dp-today': cell.iso === todayIso }">
                  <span
                    class="dp-day"
                    :class="{
                      'dp-day-selected': selectedIsos.has(cell.iso),
                      'dp-day-other': cell.otherMonth,
                    }"
                    :role="cell.otherMonth ? undefined : 'button'"
                    :tabindex="cell.otherMonth ? undefined : 0"
                    :aria-selected="selectedIsos.has(cell.iso)"
                    @click="pick(cell)"
                    @keydown.enter.prevent="pick(cell)"
                    @keydown.space.prevent="pick(cell)"
                    >{{ cell.day }}</span
                  >
                </td>
              </tr>
            </tbody>
          </table>
        </template>

        <div v-if="timeOnly" class="dp-timepicker">
          <div>
            <button type="button" class="dp-navbtn" aria-label="+" @click="stepTime('hour', 1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 15l-6-6-6 6" /></svg>
            </button>
            <span>{{ timeValue ? pad(hourFormat === "12" ? timeValue.getHours() % 12 || 12 : timeValue.getHours()) : "--" }}</span>
            <button type="button" class="dp-navbtn" aria-label="-" @click="stepTime('hour', -1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
          </div>
          <div><span>:</span></div>
          <div>
            <button type="button" class="dp-navbtn" aria-label="+" @click="stepTime('minute', 1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 15l-6-6-6 6" /></svg>
            </button>
            <span>{{ timeValue ? pad(timeValue.getMinutes()) : "--" }}</span>
            <button type="button" class="dp-navbtn" aria-label="-" @click="stepTime('minute', -1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
          </div>
        </div>

        <div v-if="showButtonBar" class="dp-buttonbar">
          <button type="button" class="dp-barbtn" @click="selectToday">{{ label.today }}</button>
          <button type="button" class="dp-barbtn" @click="clearValue">{{ label.clear }}</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Aura's datepicker geometry, with its {surface.N} / {primary.N} tokens
 * resolved to the brand variables the preset was feeding them. */
.dp {
  display: inline-flex;
  max-width: 100%;
}
.dp-fluid {
  display: flex;
}
.dp-inline {
  display: inline-block;
}
.dp-input {
  flex: 1 1 auto;
  width: 1%;
  font-family: inherit;
  font-feature-settings: inherit;
  font-size: 1rem;
  color: var(--brand-surface-900);
  background: var(--brand-surface-0);
  padding-block: 0.5rem;
  padding-inline: 0.75rem;
  border: 1px solid var(--brand-surface-200);
  border-radius: 6px;
  /* Aura's form-field shadow, with its faintly blue black flattened to
   * a neutral one: shadows carry no brand here by rule
   * (scripts/check_brand_tokens.py), and at 5% alpha the two do not
   * differ on screen. */
  box-shadow: 0 0 #0000, 0 0 #0000, 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  transition:
    background 120ms,
    color 120ms,
    border-color 120ms,
    outline-color 120ms,
    box-shadow 120ms;
  outline-color: transparent;
  appearance: none;
}
.dp-input:enabled:hover {
  border-color: var(--brand-surface-400);
}
.dp-input:enabled:focus {
  border-color: var(--brand-red);
  outline: none;
}
.dp-input::placeholder {
  color: var(--brand-surface-500);
}
.dp-input:disabled {
  opacity: 1;
  background: var(--brand-surface-50);
  color: var(--brand-surface-500);
}
</style>

<style>
/* The panel is teleported to the body, so it cannot carry the scope
 * attribute. Prefixed class names keep it to itself. */
.dp-panel {
  width: auto;
  padding: 0.75rem;
  background: var(--brand-surface);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.1),
    0 2px 4px -2px rgba(0, 0, 0, 0.1);
  z-index: 1100;
}
.dp-panel-inline {
  display: inline-block;
  overflow-x: auto;
  box-shadow: none;
  position: static;
}
.dp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 0.5rem 0;
  background: var(--brand-surface);
  color: var(--brand-text);
  border-block-end: 1px solid var(--brand-border);
}
.dp-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-weight: 500;
}
.dp-title-month {
  text-transform: capitalize;
}
/* Aura's prev/next are text-secondary rounded icon buttons. */
.dp-navbtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  flex: 0 0 auto;
  border: none;
  border-radius: 2rem;
  background: transparent;
  color: var(--brand-text-muted);
  cursor: pointer;
  transition:
    background 120ms,
    color 120ms;
}
.dp-navbtn:hover {
  background: color-mix(in srgb, var(--brand-border) 60%, transparent);
  color: var(--brand-text);
}
.dp-navbtn:active {
  background: var(--brand-border);
}
.dp-navbtn:focus-visible {
  outline: 1px solid var(--brand-red);
  outline-offset: 2px;
}
.dp-dayview {
  width: 100%;
  border-collapse: collapse;
  font-size: 1rem;
  margin: 0.5rem 0 0 0;
}
.dp-weekday-cell {
  padding: 0.25rem;
}
.dp-weekday {
  font-weight: 500;
  color: var(--brand-text-muted);
  text-transform: capitalize;
}
.dp-day-cell {
  padding: 0.25rem;
}
.dp-day {
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  margin: 0 auto;
  overflow: hidden;
  position: relative;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  border: 1px solid transparent;
  outline-color: transparent;
  color: var(--brand-text);
  transition:
    background 120ms,
    color 120ms,
    border-color 120ms,
    box-shadow 120ms,
    outline-color 120ms;
}
.dp-day:not(.dp-day-selected):not(.dp-day-other):hover {
  background: color-mix(in srgb, var(--brand-border) 60%, transparent);
  color: var(--brand-text);
}
.dp-day:focus-visible {
  outline: 1px solid var(--brand-red);
  outline-offset: 2px;
}
/* Days from the neighbouring month are shown but not selectable, which
 * is Aura's showOtherMonths without selectOtherMonths. 0.4 is the
 * preset's disabledOpacity. */
.dp-day-other {
  opacity: 0.4;
  cursor: default;
}
/* Today is the muted marker MonthGrid uses, so the two calendars agree
 * on what "today" looks like. Selected outranks it. */
.dp-today > .dp-day {
  background: var(--brand-text-muted);
  color: #fff;
  font-weight: 600;
}
.dp-day-selected,
.dp-today > .dp-day-selected {
  background: var(--brand-red);
  color: #fff;
  font-weight: normal;
}
.dp-buttonbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0 0 0;
  border-block-start: 1px solid var(--brand-border);
}
.dp-barbtn {
  border: none;
  background: transparent;
  color: var(--brand-red);
  font-family: inherit;
  font-size: 1rem;
  font-weight: 500;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background 120ms;
}
.dp-barbtn:hover {
  background: color-mix(in srgb, var(--brand-red) 8%, transparent);
}
.dp-barbtn:focus-visible {
  outline: 1px solid var(--brand-red);
  outline-offset: 2px;
}
.dp-timepicker {
  display: flex;
  justify-content: center;
  align-items: center;
  border-block-start: 1px solid var(--brand-border);
  padding: 0.5rem 0 0 0;
  gap: 0.5rem;
}
.dp-panel-timeonly .dp-timepicker {
  border-block-start: 0 none;
  padding: 0;
}
.dp-timepicker > div {
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 0.25rem;
}
.dp-timepicker span {
  font-size: 1rem;
}
</style>
