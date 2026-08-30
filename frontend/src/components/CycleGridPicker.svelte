<script lang="ts">
/**
 * Recurrence selector for one chore. Renders ``periodWeeks`` rows of
 * seven day-toggles (Mon..Sun). Each toggle maps to a flat offset into
 * the roster's k-week cycle: ``offset = week * 7 + day`` (Mon=0). For
 * k=1 it's a single weekday row, degrading to a plain weekday picker.
 *
 * The bound value is the chore's ``cycle_slots`` (a sorted ``number[]`` of
 * offsets). Kept in lock-step with the roster-level ``period_weeks`` —
 * the parent clamps out-of-range offsets when k shrinks (task 04 page).
 */
import { t } from "@/i18n.svelte";

let {
  value = $bindable(),
  periodWeeks,
}: { value: number[]; periodWeeks: number } = $props();

const dayLabels = $derived([
  t("chore.edit.weekday.mon"),
  t("chore.edit.weekday.tue"),
  t("chore.edit.weekday.wed"),
  t("chore.edit.weekday.thu"),
  t("chore.edit.weekday.fri"),
  t("chore.edit.weekday.sat"),
  t("chore.edit.weekday.sun"),
]);

const weeks = $derived(Math.max(1, periodWeeks));

function offset(week: number, day: number): number {
  return week * 7 + day;
}

function isSet(week: number, day: number): boolean {
  return value.includes(offset(week, day));
}

function toggle(week: number, day: number): void {
  const o = offset(week, day);
  const set = new Set(value);
  if (set.has(o)) set.delete(o);
  else set.add(o);
  value = [...set].sort((a, b) => a - b);
}
</script>

<div class="cycle-grid">
  {#each { length: weeks } as _, week (week)}
    <div class="cycle-week">
      <div class="day-row">
        {#each dayLabels as label, day (day)}
          <button
            type="button"
            class="day-toggle"
            class:active={isSet(week, day)}
            aria-pressed={isSet(week, day)}
            onclick={() => toggle(week, day)}
          >
            {label}
          </button>
        {/each}
      </div>
    </div>
  {/each}
</div>

<style>
.cycle-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.cycle-week {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.day-row {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}
.day-toggle {
  flex: 1 1 0;
  min-width: 2.75rem;
  padding: 0.4rem 0.25rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.day-toggle:hover {
  border-color: var(--brand-red);
}
.day-toggle.active {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #ffffff;
  font-weight: 600;
}
</style>
