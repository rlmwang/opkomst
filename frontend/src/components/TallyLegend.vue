<script setup lang="ts">
/**
 * Compact colour legend: a row of dot + label pairs, one per bar variant.
 * Shared by the chore accountability tally and the datepoll slot tally so
 * both read the same. The dot colours mirror ``SegmentedBar``'s variants.
 */
import type { SegmentVariant } from "./SegmentedBar.vue";

export interface LegendItem {
  variant: SegmentVariant;
  label: string;
}

defineProps<{ items: LegendItem[] }>();
</script>

<template>
  <div class="tally-legend muted">
    <span v-for="(item, i) in items" :key="i" class="key">
      <i class="dot" :class="`is-${item.variant}`" />{{ item.label }}
    </span>
  </div>
</template>

<style scoped>
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
