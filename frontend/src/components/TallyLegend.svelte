<script lang="ts" module>
import type { SegmentVariant } from "./SegmentedBar.svelte";

export interface LegendItem {
  variant: SegmentVariant;
  label: string;
}
</script>

<script lang="ts">
/**
 * Compact colour legend: a row of dot + label pairs, one per bar variant.
 * Shared by the chore accountability tally and the datepoll slot tally so
 * both read the same. The dot colours mirror ``SegmentedBar``'s variants.
 */
const { items }: { items: LegendItem[] } = $props();
</script>

<div class="tally-legend muted">
  {#each items as item, i (i)}
    <span class="key"><i class="dot is-{item.variant}"></i>{item.label}</span>
  {/each}
</div>

<style>
.tally-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 1rem;
  align-items: center;
  font-size: 0.8125rem;
}
.key {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
.dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  flex: none;
}
.dot.is-positive {
  background: var(--brand-green);
}
.dot.is-accent {
  background: var(--brand-blue);
}
.dot.is-warning {
  background: var(--brand-amber);
}
.dot.is-danger {
  background: var(--brand-red);
}
.dot.is-neutral {
  background: var(--brand-neutral);
}
</style>
