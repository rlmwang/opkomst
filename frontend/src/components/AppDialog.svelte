<script lang="ts">
/**
 * A modal dialog. Was a wrapper over PrimeVue's; it is the browser's own
 * ``<dialog>`` now, which does the backdrop, the top layer, the focus
 * trap and Escape without any of it being reimplemented.
 *
 * Geometry is Aura's ``overlay.modal``: a 1.25rem padding, a 12px
 * radius, and the header, body and footer spacings its dialog tokens
 * define.
 */
import type { Snippet } from "svelte";

let {
  visible = $bindable(),
  header,
  width,
  closable = true,
  children,
  footer,
}: {
  visible: boolean;
  header: string;
  width?: string;
  /** Whether the close button and Escape are offered. */
  closable?: boolean;
  children: Snippet;
  footer?: Snippet;
} = $props();

let el = $state<HTMLDialogElement>();

// ``showModal`` is what puts the dialog in the top layer and draws the
// backdrop; setting the ``open`` attribute does neither.
$effect(() => {
  if (!el) return;
  if (visible && !el.open) el.showModal();
  else if (!visible && el.open) el.close();
});

// Escape and the backdrop both fire ``cancel``; the browser closes the
// dialog either way, so the state has to follow it.
function onCancel(event: Event): void {
  if (!closable) {
    event.preventDefault();
    return;
  }
  visible = false;
}
</script>

<dialog
  bind:this={el}
  class="app-dialog"
  style="width: {width ?? '420px'}"
  oncancel={onCancel}
  onclose={() => (visible = false)}
>
  <!-- Mounted only while open. A closed <dialog> is display:none, so
       this is not about what shows; it is about not leaving a subtree
       alive with its own state and effects behind a dialog nobody is
       looking at. -->
  {#if visible}
    <div class="app-dialog-header">
      <h2 class="app-dialog-title">{header}</h2>
      {#if closable}
        <button
          type="button"
          class="app-dialog-close"
          aria-label={header}
          onclick={() => (visible = false)}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      {/if}
    </div>
    <div class="app-dialog-body">{@render children()}</div>
    {#if footer}
      <div class="app-dialog-footer">{@render footer()}</div>
    {/if}
  {/if}
</dialog>

<style>
/* Only the open one lays out: ``display`` on the element itself beats
   the browser's ``dialog:not([open]) { display: none }``, so a closed
   dialog drew as an empty strip on the page. */
.app-dialog[open] {
  display: flex;
  flex-direction: column;
}
.app-dialog {
  /* Centred. The browser's own rule zeroes the inline insets and
     leaves the block ones auto, so ``margin: auto`` had nothing to
     centre against and the dialog sat against the top of the screen.
     With every inset zeroed it centres on both axes, and the
     max-height keeps a long one on screen instead of running past the
     bottom. */
  inset: 0;
  margin: auto;
  max-height: calc(100dvh - 2rem);
  max-width: calc(100vw - 1rem);
  padding: 0;
  border: 1px solid var(--brand-border);
  border-radius: 12px;
  background: var(--brand-surface);
  color: var(--brand-text);
  box-shadow:
    0 20px 25px -5px rgba(0, 0, 0, 0.1),
    0 8px 10px -6px rgba(0, 0, 0, 0.1);
}
.app-dialog::backdrop {
  background: rgba(0, 0, 0, 0.4);
}
.app-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 1.25rem;
}
.app-dialog-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}
.app-dialog-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  flex: 0 0 auto;
  border: none;
  border-radius: 2rem;
  background: transparent;
  color: var(--brand-text-muted);
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.app-dialog-close:hover {
  background: color-mix(in srgb, var(--brand-border) 60%, transparent);
  color: var(--brand-text);
}
.app-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 0 1.25rem 1.25rem;
  /* A dialog taller than the screen scrolls here, so its title and its
     buttons stay where they are. */
  overflow: auto;
}
.app-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0 1.25rem 1.25rem;
}
</style>
