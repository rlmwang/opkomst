<script setup lang="ts">
/**
 * A modal dialog. Was a wrapper over PrimeVue's; it is the browser's own
 * ``<dialog>`` now, which does the backdrop, the top layer, the focus
 * trap and Escape without any of it being reimplemented.
 *
 * Geometry is Aura's ``overlay.modal``: a 1.25rem padding, a 12px
 * radius, and the header, body and footer spacings its dialog tokens
 * define.
 */
import { ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    visible: boolean;
    header: string;
    width?: string;
    /** Whether the close button and Escape are offered. */
    closable?: boolean;
  }>(),
  { closable: true },
);
const emit = defineEmits<{ "update:visible": [value: boolean] }>();

const el = ref<HTMLDialogElement>();

// ``showModal`` is what puts the dialog in the top layer and draws the
// backdrop; setting the ``open`` attribute does neither.
watch(
  () => props.visible,
  (open) => {
    const dialog = el.value;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  },
  { flush: "post" },
);

// Escape and the backdrop both fire ``cancel``; the browser closes the
// dialog either way, so the parent has to hear about it.
function onCancel(event: Event): void {
  if (!props.closable) {
    event.preventDefault();
    return;
  }
  emit("update:visible", false);
}
</script>

<template>
  <dialog ref="el" class="app-dialog" :style="{ width: width ?? '420px' }" @cancel="onCancel" @close="emit('update:visible', false)">
    <!-- Mounted only while open. A closed <dialog> is display:none, so
         this is not about what shows; it is about not leaving a
         subtree alive with its own state and watchers behind a dialog
         nobody is looking at. -->
    <template v-if="visible">
      <div class="app-dialog-header">
        <h2 class="app-dialog-title">{{ header }}</h2>
        <button
          v-if="closable"
          type="button"
          class="app-dialog-close"
          :aria-label="header"
          @click="emit('update:visible', false)"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="app-dialog-body">
        <slot />
      </div>
      <div v-if="$slots.footer" class="app-dialog-footer">
        <slot name="footer" />
      </div>
    </template>
  </dialog>
</template>

<style scoped>
.app-dialog {
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
}
.app-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0 1.25rem 1.25rem;
}
</style>
