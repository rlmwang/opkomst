<script setup lang="ts">
/**
 * An organisation's chapters, each tile linking to that chapter's
 * public agenda at ``/{tenant}/{chapter}``.
 *
 * Two pages show it and they must show the same thing: the public
 * front page at ``/{tenant}`` (``TenantIndexPage``), where a visitor
 * is answering "which Utrecht?", and the organiser's landing page at
 * the same path (``HomePage``), where the answer is how you reach the
 * page your own chapter publishes.
 *
 * Plain ``<a>`` rather than ``router-link``: an agenda is a separate
 * mini-app served by the backend, not a route in this bundle.
 */

defineProps<{
  chapters: { name: string; slug: string; city: string | null }[];
  /** The organisation's slug — the first segment of every agenda URL. */
  tenantSlug: string;
}>();
</script>

<template>
  <div class="chapter-grid">
    <a
      v-for="c in chapters"
      :key="c.slug"
      :href="`/${tenantSlug}/${c.slug}`"
      class="chapter-tile"
    >
      <span class="chapter-name">{{ c.name }}</span>
      <span v-if="c.city" class="muted chapter-city">{{ c.city }}</span>
    </a>
  </div>
</template>

<style scoped>
/* The same grid the agenda lays its event cards out on: up to three
 * across the wide column, dropping to two and then one as the viewport
 * narrows. One chapter per tile. */
.chapter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
  gap: 1rem;
  margin-top: 0.5rem;
}
.chapter-tile {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 4.5rem;
  padding: 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  background: var(--brand-surface);
  text-decoration: none;
  transition: border-color 120ms, background 120ms;
}
.chapter-tile:hover {
  border-color: var(--brand-red);
  background: var(--brand-red-soft);
}
.chapter-name {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--brand-red);
}
.chapter-city {
  font-size: 0.875rem;
}

@media (max-width: 380px) {
  .chapter-tile {
    min-height: 3.5rem;
    padding: 0.75rem;
    justify-content: center;
  }
  .chapter-name {
    font-size: 1rem;
  }
  .chapter-city {
    display: none;
  }
}
</style>
