<script setup lang="ts">
/**
 * A horizontal stacked bar of coloured segments, each labelled with its
 * own count. The caller passes raw counts (not widths); this owns the
 * track + fill + number styling so the tally views share one bar.
 *
 * Two scaling modes:
 *  - **normalised** (no ``max``): segments fill the whole track in
 *    proportion to each other — use when only the split matters, not the
 *    absolute size (chore accountability: a newcomer's bar shouldn't be
 *    tiny just because they've done less).
 *  - **absolute** (``max`` given): each segment is sized against a shared
 *    maximum, leaving an empty remainder when the row is below it — use
 *    when bar length should compare across rows (datepoll slots).
 *
 * Height is themeable per call via ``--segmented-bar-height``.
 */
export type SegmentVariant = "positive" | "accent" | "warning" | "danger" | "neutral";

export interface BarSegment {
  value: number;
  variant: SegmentVariant;
  title?: string;
}

const props = defineProps<{ segments: BarSegment[]; max?: number }>();

function denominator(): number {
  if (props.max != null) return Math.max(props.max, 1);
  const sum = props.segments.reduce((acc, s) => acc + Math.max(0, s.value), 0);
  return Math.max(sum, 1);
}
</script>

<template>
  <div class="segmented-bar">
    <div
      v-for="(s, i) in segments"
      v-show="s.value > 0"
      :key="i"
      class="seg"
      :class="`is-${s.variant}`"
      :style="{ width: `${(Math.max(0, s.value) / denominator()) * 100}%` }"
      :title="s.title"
    >
      <span class="seg-num">{{ s.value }}</span>
    </div>
  </div>
</template>

<style scoped>
.segmented-bar {
  display: flex;
  width: 100%;
  height: var(--segmented-bar-height, 1.5rem);
  background: var(--brand-border);
  border-radius: 6px;
  overflow: hidden;
}
.seg {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}
.seg-num {
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
  line-height: 1;
}
.seg.is-positive {
  background: var(--brand-green);
}
.seg.is-accent {
  background: var(--brand-blue);
}
.seg.is-warning {
  background: var(--brand-amber);
}
.seg.is-danger {
  background: var(--brand-red);
}
.seg.is-neutral {
  background: var(--brand-neutral);
  color: var(--brand-text);
}
</style>
