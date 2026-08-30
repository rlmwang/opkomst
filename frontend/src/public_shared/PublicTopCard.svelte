<script lang="ts">
import type { Snippet } from "svelte";

import PublicHero from "./PublicHero.svelte";

// The shared header that sits above the fold on every public entity page
// (and, via the same props, the admin details pages): the 4:5 hero with
// attribution, the title, the sanitized rich-text details, and slots for
// entity-specific meta rows and actions. One component so the same
// information places and styles identically everywhere; content
// differences live in the ``meta`` and ``actions`` snippets.
//
// ``descriptionHtml`` is pre-sanitized server-side; rendering it with
// ``{@html}`` is safe on that guarantee (see services/sanitize.py).
const {
  title,
  imageUrl,
  artist,
  creditLabel,
  descriptionHtml,
  titleExtra,
  meta,
  actions,
}: {
  title: string | null;
  imageUrl?: string | null;
  artist?: string | null;
  creditLabel?: string;
  descriptionHtml?: string | null;
  titleExtra?: Snippet;
  meta?: Snippet;
  actions?: Snippet;
} = $props();
</script>

<div class="card top-card">
  <PublicHero
    imageUrl={imageUrl ?? null}
    artist={artist ?? null}
    creditLabel={creditLabel ?? ""}
  />
  <div class="top-card-body">
    {#if title}<h1 class="top-card-title">{title}</h1>{/if}
    {#if titleExtra}{@render titleExtra()}{/if}
    {#if descriptionHtml}<div class="richtext">{@html descriptionHtml}</div>{/if}
    {#if meta}
      <dl class="top-card-meta">{@render meta()}</dl>
    {/if}
  </div>
  {#if actions}{@render actions()}{/if}
</div>

<style>
.top-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
/* Frame the hero inside the card (cancel its own bottom margin). */
.top-card :global(.hero) {
  margin-bottom: 0;
}
.top-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.top-card-title {
  margin: 0;
  font-size: 1.5rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.top-card-meta {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
}
</style>
