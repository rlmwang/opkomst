<script lang="ts">
import AdvancedFold from "@/components/AdvancedFold.svelte";
import FormSection from "@/components/FormSection.svelte";

/** A section with a bound switch, or a fold with a section in it: the
 *  two shapes a test cannot write without a parent. */
let {
  heading = "x",
  enabled = $bindable(),
  fold = false,
  open = $bindable(false),
}: { heading?: string; enabled?: boolean; fold?: boolean; open?: boolean } = $props();
</script>

{#if fold}
  <AdvancedFold bind:open>
    <FormSection heading="binnen" />
  </AdvancedFold>
{:else}
  <FormSection {heading} bind:enabled>
    <p>velden</p>
  </FormSection>
{/if}
