<script lang="ts">
/**
 * An in-app link. A real ``<a>`` with a real href, so it opens in a new
 * tab on a middle click and reads as a link to anything crawling or
 * narrating the page; the click handler is what keeps an ordinary click
 * from reloading the app.
 */
import type { Snippet } from "svelte";

import { type AnchorName, anchor } from "@/tours/anchors.svelte";

import { go, route } from "./navigation.svelte";
import { withBase } from "./router.svelte";

const {
  to,
  class: className,
  anchor: anchorName,
  children,
}: { to: string; class?: string; anchor?: AnchorName; children: Snippet } = $props();

// vue-router added this class for free and the styles rely on it: a
// subtab is styled by whether it is the page you are on.
const active = $derived(route.path === to);

function onclick(event: MouseEvent) {
  // Leave the browser to it when the visitor asked for a new tab or
  // window, or when a modifier says they meant something else.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  event.preventDefault();
  void go(to);
}
</script>

<a href={withBase(to)} class={className} class:router-link-active={active} use:anchor={anchorName} {onclick}>
  {@render children()}
</a>
