<script lang="ts">
import AppPopover from "@/components/AppPopover.svelte";

/** A popover with something in it and a button that opens it, which is
 *  every real call site. Snippets and ``bind:this`` cannot be written
 *  from a test, so they are written here. */
const { onshow, onhide }: { onshow?: () => void; onhide?: () => void } = $props();

let pop = $state<AppPopover>();
</script>

<button type="button" class="pop-trigger" onclick={(e) => pop?.toggle(e)}>open</button>
<AppPopover bind:this={pop} {onshow} {onhide}>
  <p class="pop-body">inhoud</p>
</AppPopover>
