<script lang="ts" module>
export interface StatSegment {
  width: string;
  variant?: "brand" | "positive" | "warning" | "danger" | "neutral";
  title?: string;
}
</script>

<script lang="ts">
/**
 * A horizontal stacked bar: a rounded track holding one or more coloured
 * segments at caller-supplied widths. Purely presentational — the page
 * computes each segment's width (%, normalised however it likes) and
 * picks a semantic ``variant``; this owns only the track + fill styling
 * so the four results/tally views (event ratings, form choices, datepoll
 * yes/maybe/no, chore accountability) stop each redefining it.
 *
 * Height is themeable per call via ``--stat-bar-height`` in :style.
 * The label a caller wants on the track goes on whatever wraps it.
 */
const { segments }: { segments: StatSegment[] } = $props();
</script>

<div class="stat-bar">
  {#each segments as s, i (i)}
    <div class="fill is-{s.variant ?? 'brand'}" style="width: {s.width}" title={s.title}></div>
  {/each}
</div>

<style>
.stat-bar {
  display: flex;
  width: 100%;
  height: var(--stat-bar-height, 0.625rem);
  background: var(--brand-border);
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  height: 100%;
}
.fill.is-brand {
  background: var(--brand-red);
}
.fill.is-positive {
  background: var(--brand-green);
}
.fill.is-warning {
  background: var(--brand-amber);
}
.fill.is-danger {
  background: var(--brand-red);
}
.fill.is-neutral {
  background: var(--brand-neutral);
}
</style>
