<script lang="ts">
/** Renders the app's toast queue (``lib/toast.ts``). Mounted once in
 *  ``App.vue`` for the organiser app and once in ``PublicShell`` for
 *  the public mini-apps, so both share one region and one look. */
import { onMount } from "svelte";
import { fly } from "svelte/transition";

import { currentToasts, subscribeToasts, type Toast } from "@/lib/toast";

// The queue is a plain module (``lib/toast``); this is one reactive
// view of it.
let toasts = $state<readonly Toast[]>(currentToasts());
onMount(() =>
  subscribeToasts(() => {
    toasts = currentToasts();
  }),
);
</script>

<div class="toast-region" aria-live="assertive" role="alert">
  {#each toasts as t (t.id)}
    <div class="toast" transition:fly={{ y: -8, duration: 180 }}>
      <!-- One colour for every kind; the icon is what says which it is.
           Colour-coding three shades of the same message is noise when
           toasts are this rare. -->
      {#if t.kind}
        <span class="toast-icon" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            {#if t.kind === "success"}
              <path d="M20 6L9 17l-5-5" />
            {:else if t.kind === "warn"}
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <path d="M12 9v4" /><path d="M12 17h.01" />
            {:else}
              <circle cx="12" cy="12" r="10" /><path d="M12 8v4" /><path d="M12 16h.01" />
            {/if}
          </svg>
        </span>
      {/if}
      <span class="toast-text">
        <span class="toast-summary">{t.message}</span>
        {#if t.detail}<span class="toast-detail">{t.detail}</span>{/if}
      </span>
    </div>
  {/each}
</div>

<style>
.toast-region {
  position: fixed;
  top: 1rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
  pointer-events: none;
  width: max-content;
  max-width: 90vw;
}
/* Pale primary-50 card, primary-200 border, primary-600 text. These
 * were the values primevue-preset.ts gave PrimeVue's Toast and this
 * component copied; now there is one of them. */
.toast {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  background: color-mix(in srgb, var(--brand-primary-50), transparent 5%);
  border: 1px solid var(--brand-primary-200);
  color: var(--brand-primary-600);
  padding: 0.625rem 1rem;
  border-radius: 8px;
  box-shadow: 0 4px 8px color-mix(in srgb, var(--brand-primary-500), transparent 96%);
  font-size: 0.875rem;
  line-height: 1.35;
  text-align: center;
}
.toast-icon {
  display: flex;
  flex: 0 0 auto;
  margin-top: 0.0625rem;
}
.toast-text {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  text-align: start;
}
.toast-summary {
  font-weight: 500;
}
/* The second line is the specifics, in the body colour rather than the
 * accent, so the summary still reads first. */
.toast-detail {
  color: var(--brand-text-muted);
}
</style>
