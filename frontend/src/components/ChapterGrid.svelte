<script lang="ts">
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
const {
  chapters,
  tenantSlug,
}: {
  chapters: { name: string; slug: string; city: string | null }[];
  /** The organisation's slug, the first segment of every agenda URL. */
  tenantSlug: string;
} = $props();
</script>

<div class="chapter-grid">
  {#each chapters as c (c.slug)}
    <a href="/{tenantSlug}/{c.slug}" class="chapter-tile">
      <span class="chapter-name">{c.name}</span>
      {#if c.city}<span class="muted chapter-city">{c.city}</span>{/if}
    </a>
  {/each}
</div>
