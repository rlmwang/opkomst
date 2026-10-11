<script lang="ts">
import type { Snippet } from "svelte";

import { type AnchorName, anchor } from "@/tours/anchors.svelte";

/** A card: the app's one panel. ``stack`` is the standard vertical-gap
 *  layout, on unless a caller says otherwise; ``tag`` swaps the element
 *  for a ``form`` or a ``section`` where the markup should say so.
 *
 *  Anything else passed goes straight to the element, which is how the
 *  form variant gets its ``novalidate`` and its submit handler.
 *
 *  ``class`` is taken by name and joined, not left to the spread. A
 *  spread carrying ``class`` replaces the attribute rather than adding
 *  to it, so every card given one of its own lost ``card`` and rendered
 *  with no panel at all. */
const {
  stack = true,
  tag = "div",
  class: className,
  anchor: anchorName,
  children,
  ...rest
}: {
  stack?: boolean;
  tag?: string;
  class?: string;
  /** The name a tour lights this card by (``tours/anchors``). */
  anchor?: AnchorName;
  children: Snippet;
  [key: string]: unknown;
} = $props();
</script>

<svelte:element this={tag} class="card {className ?? ''}" class:stack use:anchor={anchorName} {...rest}>
  {@render children()}
</svelte:element>
