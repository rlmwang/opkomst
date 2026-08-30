<script lang="ts">
import RosterCalendarView, { type RosterDay } from "@/components/RosterCalendarView.svelte";

/** A caller that replaces the default popover with its own content, so
 *  the test can check the snippet gets the day's assignments and a
 *  close that works. The organiser's hand-over pickers are this shape. */
const { daysByIso }: { daysByIso: Record<string, RosterDay> } = $props();
</script>

<RosterCalendarView
  month="2026-01"
  {daysByIso}
  weekdays={["ma", "di", "wo", "do", "vr", "za", "zo"]}
  prevLabel="prev"
  nextLabel="next"
  locale="nl"
  openLabel="open"
  anonLabel="anon"
>
  {#snippet popover({ assignments, close })}
    <button class="handover" onclick={() => close()}>{assignments.length}</button>
  {/snippet}
</RosterCalendarView>
