<script setup lang="ts">
/**
 * A horizontal stacked bar: a rounded track holding one or more coloured
 * segments at caller-supplied widths. Purely presentational — the page
 * computes each segment's width (%, normalised however it likes) and
 * picks a semantic ``variant``; this owns only the track + fill styling
 * so the four results/tally views (event ratings, form choices, datepoll
 * yes/maybe/no, chore accountability) stop each redefining it.
 *
 * Height is themeable per call via ``--stat-bar-height`` in :style.
 * Extra attrs (aria-label, title) fall through to the track root.
 */
export interface StatSegment {
  width: string;
  variant?: "brand" | "positive" | "warning" | "danger" | "neutral";
  title?: string;
}

defineProps<{ segments: StatSegment[] }>();
</script>

<template>
  <div class="stat-bar">
    <div
      v-for="(s, i) in segments"
      :key="i"
      class="fill"
      :class="`is-${s.variant ?? 'brand'}`"
      :style="{ width: s.width }"
      :title="s.title"
    />
  </div>
</template>

<style scoped>
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
