<script lang="ts">
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
import { untrack } from "svelte";

import { portalTarget } from "@/composables/overlay-panel";
import { useOverlayPanel } from "@/composables/useOverlayPanel.svelte";
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

let {
  modelValue = $bindable(),
  locale = "nl",
  dateFormat = "dd-mm-yy",
  placeholder,
  fluid,
  showButtonBar,
  timeOnly,
  hourFormat = "24",
  stepMinute = 1,
  inline,
  selectionMode = "single",
  manualInput = true,
  disabled,
  ariaLabel,
  onchange,
}: {
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
  /** For a caller that holds the value somewhere a two-way bind cannot
   *  reach, such as one row of an array. */
  onchange?: (value: Date | Date[] | null) => void;
} = $props();

/** Every write goes through here, so a caller gets told either way. */
function setValue(next: Date | Date[] | null): void {
  modelValue = next;
  onchange?.(next);
}

/**
 * Move the panel to the body, which is what Vue's ``<Teleport>`` did and
 * for the same reason: a panel rendered inside a form is clipped by any
 * card that hides its overflow. Its position is already the viewport's
 * (``useOverlayPanel``), so the move changes nothing but the clipping.
 */
function portal(node: HTMLElement) {
  portalTarget(overlay.anchor).appendChild(node);
  return {
    destroy() {
      node.remove();
    },
  };
}

const panelId = `dp-panel-${Math.random().toString(36).slice(2, 9)}`;

/** The composable hands back a style object; an element wants a string. */
function styleOf(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}: ${v}`)
    .join("; ");
}

const LABELS: Record<string, Record<string, string>> = {
  nl: { today: "Vandaag", clear: "Wissen", prev: "Vorige maand", next: "Volgende maand", choose: "Kies een datum" },
  en: { today: "Today", clear: "Clear", prev: "Previous month", next: "Next month", choose: "Choose a date" },
};
const label = $derived(LABELS[locale] ?? LABELS.nl);
const intlLocale = $derived(locale === "en" ? "en-GB" : "nl-NL");

let input = $state<HTMLInputElement>();
let focused = $state(false);
// The panel's placement, teleporting and dismissal
// (``composables/useOverlayPanel``), shared with the other overlays.
// Held whole, not destructured: every field is a getter.
const overlay = useOverlayPanel({ onEscape: () => input?.focus({ preventScroll: true }) });
const openPanel = overlay.show;
const hide = overlay.hide;

// --- value shape -----------------------------------------------------
// Single selection carries a Date; multiple carries an array. Everything
// below works off ``selected``, a list either way.
const selected = $derived.by<Date[]>(() => {
  const v = modelValue;
  if (!v) return [];
  return Array.isArray(v) ? v.filter(Boolean) : [v];
});

const selectedIsos = $derived(new Set(selected.map(isoOf)));
const todayIso = isoOf(new Date());

// --- the month on show ----------------------------------------------
let viewMonth = $state(monthKeyOf(untrack(() => selected)[0] ?? new Date()));
// Opening the panel lands on the selected date's month, not wherever it
// was left. A value arriving from the server after mount does the same.
// Guarded on the value rather than run on every read: an effect fires on
// mount too, and paging away and back would snap the month home.
let lastSeen: Date | undefined = untrack(() => selected)[0];
$effect(() => {
  const first = selected[0];
  if (first && first !== lastSeen) {
    lastSeen = first;
    viewMonth = monthKeyOf(first);
  }
});

const viewYear = $derived(Number(viewMonth.split("-")[0]));
const viewMonthIdx = $derived(Number(viewMonth.split("-")[1]) - 1);

function shiftMonth(delta: number): void {
  const d = new Date(viewYear, viewMonthIdx + delta, 1);
  viewMonth = monthKeyOf(d);
}

const monthTitle = $derived(
  new Date(viewYear, viewMonthIdx, 1).toLocaleDateString(intlLocale, { month: "long" }),
);

const weekdayNames = $derived.by(() => {
  // 2024-01-01 was a Monday, which is where the week starts here.
  const fmt = new Intl.DateTimeFormat(intlLocale, { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});

const weeks = $derived<Cell[][]>(monthWeeks(viewMonth));

// --- formatting and parsing -----------------------------------------
function formatTime(date: Date): string {
  return formatTimeIn(date, hourFormat);
}
function parseTime(text: string): Date | null {
  return parseTimeFrom(text, selected[0] ?? null);
}

const displayValue = $derived.by(() => {
  if (timeOnly) return selected[0] ? formatTime(selected[0]) : "";
  return selected.map((d) => formatDate(d, dateFormat)).join(", ");
});

function onInputTyped(event: Event): void {
  const text = (event.target as HTMLInputElement).value;
  if (!text.trim()) {
    setValue(selectionMode === "multiple" ? [] : null);
    return;
  }
  const parsed = timeOnly ? parseTime(text) : parseDate(text, dateFormat);
  if (!parsed) return;
  if (!timeOnly) viewMonth = monthKeyOf(parsed);
  setValue(selectionMode === "multiple" ? [parsed] : parsed);
}

// The input shows the model, except while it is being typed into: a
// reformat mid-keystroke moves the caret.
let typedText = $state("");
const inputValue = $derived(focused ? typedText : displayValue);
$effect(() => {
  typedText = displayValue;
});

// --- selection -------------------------------------------------------
function pick(cell: Cell): void {
  if (cell.otherMonth) return;
  if (selectionMode === "multiple") {
    const kept = selected.filter((d) => isoOf(d) !== cell.iso);
    setValue(kept.length === selected.length ? [...selected, cell.date] : kept);
    return;
  }
  // Keep the time a value already carried, so a picker bound to a
  // date-and-time value does not reset it to midnight.
  const next = new Date(cell.date);
  const prev = selected[0];
  if (prev) next.setHours(prev.getHours(), prev.getMinutes(), 0, 0);
  setValue(next);
  hide();
}

function stepTime(unit: "hour" | "minute", delta: number): void {
  const base = selected[0] ? new Date(selected[0]) : new Date(new Date().setSeconds(0, 0));
  if (unit === "hour") base.setHours((base.getHours() + delta + 24) % 24);
  else {
    const step = stepMinute || 1;
    const minutes = base.getMinutes() + delta * step;
    base.setMinutes(((minutes % 60) + 60) % 60);
  }
  base.setSeconds(0, 0);
  setValue(base);
}

const timeValue = $derived(selected[0] ?? null);

function selectToday(): void {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  viewMonth = monthKeyOf(now);
  setValue(selectionMode === "multiple" ? [now] : now);
  hide();
}

function clearValue(): void {
  setValue(selectionMode === "multiple" ? [] : null);
  hide();
}

// --- the overlay -----------------------------------------------------
function show(): void {
  if (disabled) return;
  // Open on the month the value is in, not wherever it was left.
  if (selected[0]) viewMonth = monthKeyOf(selected[0]);
  openPanel();
}
</script>

<div bind:this={overlay.anchor} class="dp" class:dp-fluid={fluid} class:dp-inline={inline}>
  {#if !inline}
    <input
      bind:this={input}
      type="text"
      class="dp-input"
      value={inputValue}
      placeholder={placeholder}
      {disabled}
      readonly={!manualInput}
      aria-label={ariaLabel}
      role="combobox"
      aria-controls={panelId}
      aria-expanded={overlay.open}
      aria-haspopup="dialog"
      autocomplete="off"
      onfocus={() => { focused = true; show(); }}
      onblur={() => (focused = false)}
      onclick={show}
      oninput={(e) => {
        typedText = (e.currentTarget as HTMLInputElement).value;
        onInputTyped(e);
      }}
    />
  {/if}

  <!-- Inline renders in place; the popup is teleported so no card can
       clip it. Both use the same panel markup. -->
  {#snippet calendar()}
    <div
      bind:this={overlay.panel}
      id={panelId}
      class="dp-panel"
      class:dp-panel-inline={inline}
      class:dp-panel-timeonly={timeOnly}
      style={inline ? undefined : styleOf(overlay.style)}
      role="dialog"
      aria-label={ariaLabel ?? label.choose}
    >
      {#if !timeOnly}
        <div class="dp-header">
          <button type="button" class="dp-navbtn" aria-label={label.prev} onclick={() => shiftMonth(-1)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <span class="dp-title">
            <span class="dp-title-month">{monthTitle}</span>
            <span class="dp-title-year">{viewYear}</span>
          </span>
          <button type="button" class="dp-navbtn" aria-label={label.next} onclick={() => shiftMonth(1)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        </div>

        <table class="dp-dayview">
          <thead>
            <tr>
              {#each weekdayNames as w, i (i)}
                <th class="dp-weekday-cell" scope="col"><span class="dp-weekday">{w}</span></th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each weeks as week, wi (wi)}
              <tr>
                {#each week as cell (cell.iso)}
                  <td class="dp-day-cell" class:dp-today={cell.iso === todayIso}>
                    <!-- The role and the tabindex are set by the same
                         test: a day outside this month is neither a
                         button nor reachable. -->
                    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
                    <span
                      class="dp-day"
                      class:dp-day-selected={selectedIsos.has(cell.iso)}
                      class:dp-day-other={cell.otherMonth}
                      role={cell.otherMonth ? undefined : "button"}
                      tabindex={cell.otherMonth ? undefined : 0}
                      aria-selected={selectedIsos.has(cell.iso)}
                      onclick={() => pick(cell)}
                      onkeydown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          pick(cell);
                        }
                      }}
                    >{cell.day}</span>
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      {#if timeOnly}
        <div class="dp-timepicker">
          <div>
            <button type="button" class="dp-navbtn" aria-label="+" onclick={() => stepTime("hour", 1)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 15l-6-6-6 6" /></svg></button>
            <span>{timeValue ? pad(hourFormat === "12" ? timeValue.getHours() % 12 || 12 : timeValue.getHours()) : "--"}</span>
            <button type="button" class="dp-navbtn" aria-label="-" onclick={() => stepTime("hour", -1)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg></button>
          </div>
          <div><span>:</span></div>
          <div>
            <button type="button" class="dp-navbtn" aria-label="+" onclick={() => stepTime("minute", 1)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 15l-6-6-6 6" /></svg></button>
            <span>{timeValue ? pad(timeValue.getMinutes()) : "--"}</span>
            <button type="button" class="dp-navbtn" aria-label="-" onclick={() => stepTime("minute", -1)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg></button>
          </div>
        </div>
      {/if}

      {#if showButtonBar}
        <div class="dp-buttonbar">
          <button type="button" class="dp-barbtn" onclick={selectToday}>{label.today}</button>
          <button type="button" class="dp-barbtn" onclick={clearValue}>{label.clear}</button>
        </div>
      {/if}
    </div>
  {/snippet}

  {#if inline}
    {@render calendar()}
  {:else if overlay.open}
    <div use:portal style="display: contents">{@render calendar()}</div>
  {/if}
</div>

<style>
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
