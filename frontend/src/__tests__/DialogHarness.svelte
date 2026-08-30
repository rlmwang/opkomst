<script lang="ts">
import AppDialog from "@/components/AppDialog.svelte";

/** A dialog with a body and a footer in it, which is every real call
 *  site. Snippets cannot be written from a test, so they are written
 *  here. */
let {
  visible = $bindable(),
  header,
  closable = true,
  withFooter = true,
}: { visible: boolean; header: string; closable?: boolean; withFooter?: boolean } = $props();
</script>

<AppDialog bind:visible {header} {closable}>
  <p>inhoud</p>
  {#snippet footer()}
    {#if withFooter}<button>Ok</button>{/if}
  {/snippet}
</AppDialog>
