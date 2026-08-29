<script lang="ts">
const {
  rows = 3,
  cards = false,
}: {
  /** Number of skeleton rows to render. */
  rows?: number;
  /** Render as cards (each row inside a stack-like card frame) rather
   *  than plain bars, matching the look of the data the skeleton is
   *  standing in for. */
  cards?: boolean;
} = $props();
</script>

<div class="skeleton" class:skeleton--cards={cards}>
  {#each { length: rows } as _, i (i)}
    <div class="skeleton-row"></div>
  {/each}
</div>

<style>
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
