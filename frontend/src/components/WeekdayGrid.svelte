<script lang="ts">
/**
 * Read-only weekday grid — the display twin of ``CycleGridPicker``.
 * Renders ``periodWeeks`` rows of seven day cells (Mon..Sun), the active
 * ones (in ``cycleSlots``, offset = week*7 + day) highlighted. Pure and
 * dependency-free (labels are passed in), so both the admin details page
 * and the public mini-app can use it without pulling in i18n.
 */
const {
  cycleSlots,
  periodWeeks,
  weekdayLabels,
}: {
  cycleSlots: number[];
  periodWeeks: number;
  /** Seven weekday labels, Mon..Sun. */
  weekdayLabels: readonly string[];
} = $props();

const weeks = $derived(Math.max(1, periodWeeks));

function isSet(week: number, day: number): boolean {
  return cycleSlots.includes(week * 7 + day);
}
</script>

<div class="weekday-grid">
  {#each { length: weeks } as _, week (week)}
    <div class="wg-row">
      {#each weekdayLabels as label, day (day)}
        <span class="wg-day" class:active={isSet(week, day)}>{label}</span>
      {/each}
    </div>
  {/each}
</div>

<style>
.weekday-grid {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.wg-row {
  display: flex;
  gap: 0.25rem;
}
.wg-day {
  flex: 1 1 0;
  min-width: 2rem;
  text-align: center;
  padding: 0.25rem 0.2rem;
  border: 1px solid var(--brand-border);
  border-radius: 5px;
  font-size: 0.75rem;
  color: var(--brand-text-muted);
  background: var(--brand-surface);
}
.wg-day.active {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #ffffff;
  font-weight: 600;
}
</style>
