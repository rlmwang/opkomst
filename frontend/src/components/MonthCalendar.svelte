<script lang="ts">
/**
 * A datepoll's proposed days as a calendar, built on the shared
 * ``MonthGrid`` (so it matches the roster calendars). Candidate days render
 * as occurrence cells showing their time range(s); whole-day slots show the
 * day alone. Read-only, month-navigable.
 */
import MonthGrid from "./MonthGrid.svelte";

interface Slot {
  on_date: string;
  start_time?: string | null;
  end_time?: string | null;
}

let {
  month = $bindable(),
  slots,
  locale,
  prevLabel,
  nextLabel,
}: {
  month: string; // YYYY-MM
  slots: Slot[];
  locale: string;
  prevLabel: string;
  nextLabel: string;
} = $props();

const byIso = $derived.by(() => {
  const m = new Map<string, string[]>();
  for (const s of slots) {
    if (!m.has(s.on_date)) m.set(s.on_date, []);
    if (s.start_time && s.end_time)
      m.get(s.on_date)!.push(`${s.start_time.slice(0, 5)}\u2013${s.end_time.slice(0, 5)}`);
  }
  return m;
});
const weekdays = $derived.by(() => {
  const fmt = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
function dayClass(iso: string) {
  return { occ: byIso.has(iso) };
}
</script>

<MonthGrid bind:month {locale} {weekdays} {prevLabel} {nextLabel} {dayClass}>
  {#snippet day({ iso })}
    {#if byIso.get(iso)?.length}
      <ul class="mc-times">
        {#each byIso.get(iso) ?? [] as time, j (j)}
          <li>{time}</li>
        {/each}
      </ul>
    {/if}
  {/snippet}
</MonthGrid>

<style>
.mc-times {
  list-style: none;
  margin: 0;
  padding: 0;
}
.mc-times li {
  font-size: 0.6875rem;
  line-height: 1.25;
}
</style>
