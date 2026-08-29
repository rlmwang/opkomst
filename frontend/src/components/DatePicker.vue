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
 * semantic tokens: ``--brand-text``, ``--brand-text-muted`` and
 * ``--brand-border``, which is what ``MonthGrid``, ``AppInput`` and
 * every other hand-rolled control read.
 *
 * Month and weekday names come from ``Intl`` in the page language, the
 * way ``MonthGrid`` does. PrimeVue was configured with only
 * ``firstDayOfWeek``, so its default English locale showed through and
 * every picker in the app read "March" over "Mo Tu We" on a Dutch page.
 *
 * No admin dependencies: the public chore page imports this directly.
 */
import { computed, ref, watch } from "vue";

import { useOverlayPanel } from "@/composables/useOverlayPanel";
import "./date-picker.css";
import {
  type Cell,
  formatDate,
  formatTime as formatTimeIn,
  isoOf,
  monthKeyOf,
  monthWeeks,
  pad,
  parseDate,
  parseTime as parseTimeFrom,
} from "./date-picker";

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

const input = ref<HTMLInputElement>();
const focused = ref(false);
// The panel's placement, teleporting and dismissal
// (``composables/useOverlayPanel``), shared with the other overlays.
const { anchor: root, panel, open, style: panelStyle, show: openPanel, hide } = useOverlayPanel({
  onEscape: () => input.value?.focus(),
});

// --- value shape -----------------------------------------------------
// Single selection carries a Date; multiple carries an array. Everything
// below works off ``selected``, a list either way.
const selected = computed<Date[]>(() => {
  const v = props.modelValue;
  if (!v) return [];
  return Array.isArray(v) ? v.filter(Boolean) : [v];
});

const selectedIsos = computed(() => new Set(selected.value.map(isoOf)));
const todayIso = isoOf(new Date());

// --- the month on show ----------------------------------------------
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

const weeks = computed<Cell[][]>(() => monthWeeks(viewMonth.value));

// --- formatting and parsing -----------------------------------------
function formatTime(date: Date): string {
  return formatTimeIn(date, props.hourFormat);
}
function parseTime(text: string): Date | null {
  return parseTimeFrom(text, selected.value[0] ?? null);
}

const displayValue = computed(() => {
  if (props.timeOnly) return selected.value[0] ? formatTime(selected.value[0]) : "";
  return selected.value.map((d) => formatDate(d, props.dateFormat)).join(", ");
});

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
function show(): void {
  if (props.disabled) return;
  // Open on the month the value is in, not wherever it was left.
  if (selected.value[0]) viewMonth.value = monthKeyOf(selected.value[0]);
  openPanel();
}
</script>

<template>
  <div ref="root" class="dp" :class="{ 'dp-fluid': fluid, 'dp-inline': inline }">
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
  color: var(--brand-text);
  background: var(--brand-surface);
  padding-block: 0.5rem;
  padding-inline: 0.75rem;
  border: 1px solid var(--brand-border);
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
  border-color: color-mix(in srgb, var(--brand-text-muted) 45%, transparent);
}
.dp-input:enabled:focus {
  border-color: var(--brand-red);
  outline: none;
}
.dp-input::placeholder {
  color: var(--brand-text-muted);
}
.dp-input:disabled {
  opacity: 1;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
}
</style>
