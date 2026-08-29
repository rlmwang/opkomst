<script lang="ts">
/**
 * The shared monthly-calendar shell used by every calendar in the app
 * (admin roster + fold-in preview, public personal page, datepoll date
 * overview). Owns everything that must look identical: the ‹ month ›
 * navigator, Monday-first weekday header, a fixed six-week grid (so height
 * doesn't jump between months), the day number, and the "today" marker.
 *
 * Callers style each day via ``dayClass(iso)`` (e.g. occurrence / tentative
 * / changed) and fill its body through the ``day`` snippet. Set
 * ``clickable(iso)`` to make a day a full-cell button that emits
 * ``ondayClick`` (the body snippet then renders any anchored popover). No
 * admin deps — safe to import from the public mini-apps.
 */
import type { Snippet } from "svelte";

import {
  type Cell,
  columnTemplate as columnsFor,
  isoOf,
  monthCells,
  monthLabel as labelFor,
  shiftMonth,
} from "./month-grid";

let {
  month = $bindable(),
  locale,
  weekdays,
  prevLabel,
  nextLabel,
  nav = true,
  dayClass,
  clickable,
  activeIso,
  columns,
  day,
  ondayClick,
}: {
  month: string; // YYYY-MM
  locale: string;
  weekdays: readonly string[];
  prevLabel?: string;
  nextLabel?: string;
  /** Show the month navigator. Off for stacked-months views (datepoll
   *  voting) that render one grid per month with a plain title. */
  nav?: boolean;
  dayClass?: (iso: string) => Record<string, boolean> | undefined;
  clickable?: (iso: string) => boolean;
  /** The day whose snippet currently renders an open popover: it is
   *  lifted into its own stacking context above sibling cells so the
   *  popover and its buttons sit on top and receive hover and clicks. */
  activeIso?: string | null;
  /** An explicit ``grid-template-columns`` shared by the header and
   *  every stacked grid. Callers that render several months at once
   *  (datepoll) pass one fixed template so the day columns line up
   *  across months and with the weekday header. Unset: each grid sizes
   *  its own columns by which carry content. */
  columns?: string;
  day?: Snippet<[{ iso: string; day: number }]>;
  /** A day the caller made clickable was pressed. */
  ondayClick?: (iso: string) => void;
} = $props();

const todayIso = isoOf(new Date());
const monthLabel = $derived(labelFor(month, locale));
const cells = $derived<Cell[]>(monthCells(month, todayIso));
const columnTemplate = $derived(columnsFor(cells, dayClass));

function shift(delta: number) {
  month = shiftMonth(month, delta);
}

function isClickable(c: Cell): boolean {
  return !!(c.iso && clickable?.(c.iso));
}
function onCellClick(c: Cell) {
  // The popover (rendered in the day snippet) stops its own clicks, so
  // this only fires for a bare tap on the day cell.
  if (c.iso && clickable?.(c.iso)) ondayClick?.(c.iso);
}
</script>

<div class="mg">
  {#if nav !== false}
    <div class="mg-nav">
      <button type="button" class="mg-navbtn" aria-label={prevLabel} onclick={() => shift(-1)}>‹</button>
      <span class="mg-month">{monthLabel}</span>
      <button type="button" class="mg-navbtn" aria-label={nextLabel} onclick={() => shift(1)}>›</button>
    </div>
  {:else}
    <p class="mg-title">{monthLabel}</p>
  {/if}
  <div class="mg-dow" style="grid-template-columns: {columns ?? columnTemplate}">
    {#each weekdays as w, i (i)}<span>{w}</span>{/each}
  </div>
  <div class="mg-grid" style="grid-template-columns: {columns ?? columnTemplate}">
    {#each cells as c, i (i)}
      {@const extra = c.day && dayClass ? dayClass(c.iso!) : undefined}
      <!-- The role and the tabindex are set by the same test, so a cell
           is either a button or is not reachable at all. The check
           cannot see that the two are one decision. -->
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div
        class="mg-cell"
        class:occ={extra?.occ}
        class:tentative={extra?.tentative}
        class:changed={extra?.changed}
        class:today={c.today}
        class:clickable={!!c.day && isClickable(c)}
        class:is-active={!!c.iso && c.iso === activeIso}
        role={c.day && isClickable(c) ? "button" : undefined}
        tabindex={c.day && isClickable(c) ? 0 : undefined}
        aria-label={c.day && isClickable(c) ? String(c.day) : undefined}
        onclick={() => onCellClick(c)}
        onkeydown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onCellClick(c);
          }
        }}
      >
        {#if c.day}
          <span class="mg-num">{c.day}</span>
          <div class="mg-body">
            {#if day}{@render day({ iso: c.iso!, day: c.day })}{/if}
          </div>
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
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
/* An "occurrence" day (caller opts in via dayClass): bordered card. A
 * higher-contrast border than the surrounding chrome so locked ("vast") days
 * read clearly; tentative ("voorlopig") days are the same border, dashed. */
.mg-cell.occ {
  border: 1px solid color-mix(in srgb, var(--brand-text-muted) 42%, var(--brand-border));
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
