<script module lang="ts">
export interface Tile {
  key: string;
  to: string;
  label: string;
  hint: string;
  /** Spans the row. For the one tile that acts on the organisation
   *  rather than on its programme. */
  wide?: boolean;
}
</script>

<script lang="ts">
import RouterLink from "@/router/RouterLink.svelte";

/**
 * The tiles both landing faces are made of.
 *
 * Signed out, a tile opens the create form for one of the six things
 * this tool makes; signed in, it opens that thing's workspace. Either
 * way it is the same object, so it is drawn in one place.
 *
 * Two columns at every width. The tiles are the whole page, and a
 * single column would push half of them below the fold on a phone. On
 * the narrowest phones the hint goes first, because two words per line
 * reads worse than no line at all, and the tiles shrink to the label
 * they are left with.
 */
const { tiles, gap = "1rem" }: { tiles: Tile[]; gap?: string } = $props();
</script>

<div class="tile-grid" style:gap>
  {#each tiles as tile (tile.key)}
    <RouterLink to={tile.to} class={tile.wide ? "tile tile-wide" : "tile"}>
      <span class="tile-label">{tile.label}</span>
      <span class="tile-hint muted">{tile.hint}</span>
    </RouterLink>
  {/each}
</div>

<style>
.tile-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  margin-top: 0.5rem;
}
.tile-grid :global(.tile) {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 6.5rem;
  padding: 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  background: var(--brand-surface);
  color: var(--brand-text);
  text-decoration: none;
  transition: border-color 120ms, background 120ms, transform 120ms;
}
.tile-grid :global(.tile:hover) {
  border-color: var(--brand-red);
  background: var(--brand-red-soft);
}
.tile-grid :global(.tile:active) {
  transform: translateY(1px);
}
.tile-grid :global(.tile-wide) {
  grid-column: 1 / -1;
  flex-direction: row;
  align-items: baseline;
  gap: 0.625rem;
  min-height: 0;
  flex-wrap: wrap;
}
.tile-label {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--brand-red);
}
.tile-hint {
  font-size: 0.875rem;
  line-height: 1.35;
}

@media (max-width: 380px) {
  .tile-grid :global(.tile) {
    min-height: 3.5rem;
    padding: 0.75rem;
    justify-content: center;
  }
  .tile-grid :global(.tile-wide) {
    min-height: 0;
  }
  .tile-label {
    font-size: 1rem;
  }
  .tile-hint {
    display: none;
  }
}
</style>
