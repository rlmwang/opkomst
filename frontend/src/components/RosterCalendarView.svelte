<script lang="ts" module>
export interface RosterAction {
  shiftId: string;
  kind: string;
  label: string;
}
export interface RosterAssignment {
  emoji: string | null;
  name: string | null; // assignee pseudonym; null = open slot
  open: boolean;
  status: string; // scheduled | done | missed
  choreId?: string; // set by callers whose popover needs the chore (organiser hand-over)
  action?: RosterAction;
}
export interface RosterDay {
  assignments: RosterAssignment[];
  tentative: boolean;
  changed: boolean;
}
</script>

<script lang="ts">
/**
 * The one merged-roster month calendar, shared by the organiser details page
 * and the public "Bijspringen" overview. Presentational + dependency-free:
 * the caller supplies ``daysByIso`` (each chore's assignments folded per
 * date, emoji-tagged) and this renders them on the shared ``MonthGrid`` —
 * emoji + assignee per row, open in red, done ticked, missed struck through,
 * tentative days dashed, changed days ringed.
 *
 * Any assignment carrying an ``action`` makes its day tappable, opening a
 * popover. The default popover renders one button per action (the public
 * view's claim/cover); the ``popover`` snippet lets a caller render its own
 * content instead (the organiser's hand-over pickers). While a popover is
 * open every other day is inert — a click only dismisses it.
 */
import { onMount, type Snippet } from "svelte";

import MonthGrid from "./MonthGrid.svelte";

let {
  month = $bindable(),
  daysByIso,
  weekdays,
  prevLabel,
  nextLabel,
  locale,
  openLabel,
  anonLabel,
  busy,
  popover,
  onact,
}: {
  month: string; // YYYY-MM
  daysByIso: Record<string, RosterDay>;
  weekdays: readonly string[];
  prevLabel: string;
  nextLabel: string;
  locale: string;
  openLabel: string;
  anonLabel: string;
  busy?: boolean;
  popover?: Snippet<[{ iso: string; assignments: RosterAssignment[]; close: () => void }]>;
  onact?: (shiftId: string, kind: string) => void;
} = $props();

function dayClass(iso: string) {
  const d = daysByIso[iso];
  return { occ: !!d?.assignments.length, tentative: !!d?.tentative, changed: !!d?.changed };
}
function actionable(iso: string): boolean {
  return (daysByIso[iso]?.assignments ?? []).some((a) => a.action);
}

let openIso = $state<string | null>(null);
// While a popover is open every other day is inert (no hover, no click):
// a click only dismisses the popover, which also avoids a double-toggle
// race between opening one day and closing another.
function dayIsClickable(iso: string): boolean {
  return openIso === null && actionable(iso);
}
const openActions = $derived<RosterAction[]>(
  openIso
    ? (daysByIso[openIso]?.assignments ?? []).flatMap((a) => (a.action ? [a.action] : []))
    : [],
);
function onDayClick(iso: string) {
  openIso = openIso === iso ? null : iso;
}
function doAct(a: RosterAction) {
  openIso = null;
  onact?.(a.shiftId, a.kind);
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
    {#if daysByIso[iso]?.assignments.length}
      <ul class="rcv-list">
        {#each daysByIso[iso].assignments as a, j (j)}
          <li
            class="rcv-item"
            class:open={a.open}
            class:done={a.status === "done"}
            class:missed={a.status === "missed"}
          >
            {#if a.emoji}<span class="rcv-emoji" aria-hidden="true">{a.emoji}</span>{/if}
            <span class="rcv-name"
              >{a.open ? `(${openLabel})` : a.name || anonLabel}{#if a.status === "done"}<span
                  class="rcv-check"
                  aria-hidden="true"
                >
                  ✓</span
                >{/if}</span
            >
          </li>
        {/each}
      </ul>
    {/if}
    {#if openIso === iso}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="rcv-pop" onclick={(e) => e.stopPropagation()}>
        {#if popover}
          {@render popover({ iso, assignments: daysByIso[iso]?.assignments ?? [], close })}
        {:else}
          {#each openActions as a, j (j)}
            <button type="button" class="btn" disabled={busy} onclick={() => doAct(a)}>
              {a.label}
            </button>
          {/each}
        {/if}
      </div>
    {/if}
  {/snippet}
</MonthGrid>

<style>
.rcv-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rcv-item {
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
  font-size: 0.75rem;
  line-height: 1.3;
}
.rcv-emoji {
  flex-shrink: 0;
}
.rcv-item.open .rcv-name {
  color: var(--brand-red);
}
.rcv-item.done .rcv-name {
  color: var(--brand-text-muted);
}
.rcv-item.missed .rcv-name {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
.rcv-check {
  color: var(--brand-green);
}
/* Claim/cover popover — matches the public ``.btn`` action buttons. */
.rcv-pop {
  pointer-events: auto;
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 11rem;
  max-width: 15rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  text-align: left;
}
/* The public mini-apps ship ``.btn`` from forms.css; the organiser app
 * does not, so provide the equivalent here for the read-only view (it
 * has no buttons anyway, but keep the popover self-sufficient). */
.rcv-pop .btn {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  cursor: pointer;
}
.rcv-pop .btn:hover:not(:disabled) {
  background: var(--brand-red-soft);
  border-color: var(--brand-red-soft-border);
}
</style>
