<script setup lang="ts">
withDefaults(
  defineProps<{
    /** Number of skeleton rows to render. */
    rows?: number;
    /** Render as cards (each row inside a stack-like card frame)
     * rather than plain bars — matches the look of the data the
     * skeleton is standing in for. */
    cards?: boolean;
  }>(),
  { rows: 3, cards: false },
);
</script>

<template>
  <div :class="['skeleton', { 'skeleton--cards': cards }]">
    <div v-for="i in rows" :key="i" class="skeleton-row" />
  </div>
</template>

<style scoped>
.skeleton {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.skeleton-row {
  height: 3.5rem;
  border-radius: 8px;
  background: linear-gradient(
    90deg,
    var(--brand-bg) 0%,
    var(--brand-surface) 50%,
    var(--brand-bg) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s ease-in-out infinite;
}
.skeleton--cards .skeleton-row {
  height: 6rem;
  border: 1px solid var(--brand-border);
}
@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
