<script lang="ts">
import AppDialog from "@/components/AppDialog.svelte";
import MultiSelectField from "@/components/MultiSelectField.svelte";

/** A picker inside a modal, which is where the admin's chapter field
 *  lives. Snippets cannot be written from a test, so the dialog's
 *  footer is written here. */
let {
  value = $bindable(),
  options,
}: { value: string[]; options: { id: string; name: string }[] } = $props();
</script>

<AppDialog visible header="Bewerken">
  <label>
    Afdelingen
    <MultiSelectField bind:value {options} optionLabel="name" optionValue="id" display="chip" fluid />
  </label>
  {#snippet footer()}<button>Ok</button>{/snippet}
</AppDialog>
