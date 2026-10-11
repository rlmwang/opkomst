<script lang="ts">
import type { Snippet } from "svelte";

import AppToggle from "@/components/AppToggle.svelte";
import { type AnchorName, anchor } from "@/tours/anchors.svelte";

/**
 * One block of an edit page: a heading, an optional switch in front of
 * it that turns the block on, an optional explainer, then the fields.
 *
 * The four edit pages wrote this by hand 29 times, 15 of them with the
 * switch, each wiring its own label id. Now the id is the component's
 * (``$props.id()``), the switch is the heading's label because the
 * heading sits inside the ``<label>``, and a section has a tour anchor
 * by existing (``docs/design-tour.md`` chapter 10).
 *
 * ``enabled`` is bound only where a switch belongs; left unbound, the
 * heading is a plain heading. No heading at all is a section of bare
 * fields, which is what the first block of every form is.
 */
let {
  heading,
  enabled = $bindable(),
  explainer,
  anchor: anchorName,
  children,
}: {
  heading?: string;
  /** Bind it and the heading becomes a toggle row. */
  enabled?: boolean;
  explainer?: string;
  /** The name a tour lights this section by. */
  anchor?: AnchorName;
  children?: Snippet;
} = $props();

const toggleId = $props.id();
</script>

<section class="form-section" use:anchor={anchorName}>
  {#if heading && enabled !== undefined}
    <label class="toggle-row" for={toggleId}>
      <AppToggle bind:checked={() => enabled ?? false, (v) => (enabled = v)} inputId={toggleId} />
      <h2 class="section-heading">{heading}</h2>
    </label>
  {:else if heading}
    <h2 class="section-heading">{heading}</h2>
  {/if}
  {#if explainer}<p class="muted section-explainer">{explainer}</p>{/if}
  {#if children}{@render children()}{/if}
</section>
