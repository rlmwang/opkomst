<script lang="ts">
/** A search field with the magnifier sitting inside it. The icon and
 *  its clearance were PrimeVue's ``IconField`` / ``InputIcon``, which
 *  is a wrapper, an absolutely-positioned icon, and padding on the
 *  input. That is cheaper written here than imported. */
import AppInput from "@/components/AppInput.svelte";
import AppIcon from "@/components/AppIcon.svelte";

let {
  value = $bindable(""),
  placeholder,
  class: className,
}: { value: string; placeholder: string; class?: string } = $props();
</script>

<div class="icon-field {className ?? ''}">
  <AppIcon name="search" />
  <AppInput bind:value {placeholder} fluid />
</div>

<style>
.icon-field {
  position: relative;
  display: block;
}
.icon-field :global(.app-icon) {
  position: absolute;
  top: 50%;
  inset-inline-start: 0.75rem;
  margin-top: -0.5rem;
  color: var(--brand-text-muted);
  z-index: 1;
}
/* Twice the field's own inline padding, plus the icon, so the text
 * starts clear of it. */
.icon-field :global(.app-input) {
  padding-inline-start: 2.5rem;
}
</style>
