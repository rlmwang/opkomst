<script lang="ts">
/** Renders whatever ``useConfirms().ask`` last asked (``lib/confirms``).
 *  Mounted once in ``App.vue``, the way PrimeVue's ConfirmDialog was. */
import AppButton from "@/components/AppButton.svelte";
import AppDialog from "@/components/AppDialog.svelte";
import AppIcon from "@/components/AppIcon.svelte";
import { acceptConfirm, currentConfirm, rejectConfirm } from "@/lib/confirms.svelte";

const request = $derived(currentConfirm());

// The dialog closes itself on Escape and on the close button; either is
// a decision not to go ahead.
let open = $derived(request !== null);
</script>

{#if request}
  <AppDialog
    bind:visible={
      () => open,
      (v) => {
        if (!v) rejectConfirm();
      }
    }
    header={request.header}
  >
    <p class="confirm-message">
      {#if request.icon}<AppIcon name={request.icon} />{/if}
      <span>{request.message}</span>
    </p>
    {#snippet footer()}
      <AppButton label={request.rejectLabel} severity="secondary" text onclick={rejectConfirm} />
      <AppButton label={request.acceptLabel} onclick={acceptConfirm} />
    {/snippet}
  </AppDialog>
{/if}

<style>
.confirm-message {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0;
}
</style>
