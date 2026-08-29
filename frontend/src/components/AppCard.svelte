<script lang="ts">
import type { Snippet } from "svelte";

/** A card: the app's one panel. ``stack`` is the standard vertical-gap
 *  layout, on unless a caller says otherwise; ``tag`` swaps the element
 *  for a ``form`` or a ``section`` where the markup should say so. */
const {
  stack = true,
  tag = "div",
  children,
}: { stack?: boolean; tag?: string; children: Snippet } = $props();
</script>

<svelte:element this={tag} class="card" class:stack>
  {@render children()}
</svelte:element>
