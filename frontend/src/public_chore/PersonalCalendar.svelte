<script lang="ts" module>
import type { ShiftAction } from "./api";

export interface CalAction {
  key: ShiftAction;
  label: string;
  ghost?: boolean;
}
export interface CalEntry {
  id: string | null; // null = not actionable (expected/tentative)
  choreName: string;
  tentative: boolean;
  done?: boolean; // completed — shown ticked off, non-actionable
  missed?: boolean; // past, never done — shown struck through
  note?: string; // shown inline after the chore name in the popover
  actions?: CalAction[];
}
</script>

<script lang="ts">
/**
 * Public personal-page calendar, built on the shared ``MonthGrid`` so it
 * matches the admin roster calendars exactly. Shows the volunteer's tasks
 * per day (chore names, comma-separated); confirmed days are solid,
 * tentative (expected) days dashed. Clicking a day that holds an actionable
 * shift opens a small popover with its action buttons.
 */
import { onMount } from "svelte";

import MonthGrid from "@/components/MonthGrid.svelte";
import type { Locale } from "@/public_shared/strings";

let {
  month = $bindable(),
  entriesByDate,
  weekdays,
  prevLabel,
  nextLabel,
  locale,
  busy,
  onact,
}: {
  month: string; // YYYY-MM
  entriesByDate: Record<string, CalEntry[]>;
  weekdays: readonly string[];
  prevLabel: string;
  nextLabel: string;
  locale: Locale;
  busy?: boolean;
  onact?: (id: string, key: ShiftAction) => void;
} = $props();

let openIso = $state<string | null>(null);

function dayClass(iso: string) {
  const es = entriesByDate[iso];
  return { occ: !!es?.length, tentative: !!es?.[0]?.tentative };
}
function actionable(iso: string): boolean {
  return (entriesByDate[iso] ?? []).some((e) => e.id && (e.actions?.length ?? 0) > 0);
}
// While a popover is open every other day is inert (no hover, no click):
// a click only dismisses the popover, which also avoids a double-toggle
// race.
function dayIsClickable(iso: string): boolean {
  return openIso === null && actionable(iso);
}

const openEntries = $derived(
  openIso ? (entriesByDate[openIso] ?? []).filter((e) => e.id && e.actions?.length) : [],
);
function onDayClick(iso: string) {
  openIso = openIso === iso ? null : iso;
}
function doAct(id: string, key: ShiftAction) {
  openIso = null;
  onact?.(id, key);
}
function close() {
  openIso = null;
}

// The listener goes on after the click that opened the popover has
// finished bubbling, or it would close it again immediately.
$effect(() => {
  if (!openIso) return;
  const id = setTimeout(() => document.addEventListener("click", close), 0);
  return () => {
    clearTimeout(id);
    document.removeEventListener("click", close);
  };
});
onMount(() => () => document.removeEventListener("click", close));
</script>

<MonthGrid
  bind:month
  {locale}
  {weekdays}
  {prevLabel}
  {nextLabel}
  {dayClass}
  clickable={dayIsClickable}
  activeIso={openIso}
  ondayClick={onDayClick}
>
  {#snippet day({ iso })}
    {#if entriesByDate[iso]}
      <ul class="pcal-names">
        {#each entriesByDate[iso] as e, j (j)}
          <li class:done={e.done} class:missed={e.missed}>
            {e.choreName}{#if e.done}<span class="pcal-check" aria-hidden="true"> ✓</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}
    {#if openIso === iso}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="pcal-pop" onclick={(e) => e.stopPropagation()}>
        {#each openEntries as e, j (j)}
          <div class="pcal-pop-item">
            <div class="pcal-pop-title">
              {e.choreName}{#if e.note}<span class="pcal-pop-for"> &middot; {e.note}</span>{/if}
            </div>
            <div class="pcal-pop-actions">
              {#each e.actions ?? [] as a (a.key)}
                <button
                  type="button"
                  class="btn"
                  class:ghost={a.ghost}
                  disabled={busy}
                  onclick={() => e.id && doAct(e.id, a.key)}
                >
                  {a.label}
                </button>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/snippet}
</MonthGrid>

<style>
.pcal-names {
  list-style: none;
  margin: 0;
  padding: 0;
}
.pcal-names li {
  display: inline;
  font-size: 0.75rem;
  line-height: 1.3;
}
.pcal-names li:not(:last-child)::after {
  content: ", ";
  color: var(--brand-text-muted);
}
/* Finished shifts: done ticked off (green check), missed struck through. */
.pcal-names li.done {
  color: var(--brand-text-muted);
}
.pcal-names li.missed {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
.pcal-check {
  color: var(--brand-green);
}
.pcal-pop {
  pointer-events: auto;
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 12rem;
  max-width: 15rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  padding: 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  text-align: left;
}
.pcal-pop-title {
  font-weight: 600;
}
.pcal-pop-for {
  color: var(--brand-text-muted);
  font-weight: 400;
}
.pcal-pop-actions {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.5rem;
}
</style>
