<script setup lang="ts">
// One line of entity metadata: a brand-red icon (slot) followed by its
// value (default slot). Extracted from the event header so every top
// card, public or admin, renders date / time / location the same way.
// When ``href`` is set the value becomes a link with the shared inherit
// -colour + external-icon treatment.
defineProps<{ href?: string }>();
</script>

<template>
  <div class="meta-row">
    <span class="icon"><slot name="icon" /></span>
    <a
      v-if="href"
      class="meta-link"
      :href="href"
      target="_blank"
      rel="noopener noreferrer"
    >
      <slot />
      <svg class="external" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
        <polyline points="15 3 21 3 21 9" />
        <line x1="10" y1="14" x2="21" y2="3" />
      </svg>
    </a>
    <span v-else><slot /></span>
  </div>
</template>

<style scoped>
.meta-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.95rem;
  line-height: 1.3;
}
.meta-row > .icon {
  color: var(--brand-red);
  width: 1rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.meta-link {
  color: inherit;
  text-decoration: none;
}
.meta-link:hover {
  text-decoration: underline;
  text-decoration-color: var(--brand-red);
}
.meta-link .external {
  color: var(--brand-text-muted);
  margin-left: 0.3rem;
  vertical-align: -1px;
}
</style>
