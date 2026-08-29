<script setup lang="ts">
/**
 * The app's on/off switch. Replaces PrimeVue's ``ToggleSwitch``, across
 * 18 call sites.
 *
 * Geometry is Aura's: a 2.5rem by 1.5rem track with a 1rem handle and
 * 0.25rem of clearance. The colours are the preset's own override, not
 * Aura's, because ``primevue-preset.ts`` had already restyled this one
 * to sit properly on the cream surfaces.
 *
 * A real checkbox underneath, transparent and stretched over the track,
 * so the keyboard, the label association and the accessibility tree all
 * work without anything being reimplemented.
 */
defineProps<{
  disabled?: boolean;
  /** Set when a ``<label for=...>`` elsewhere points at this switch. */
  inputId?: string;
}>();
// Defaulted, so the emitted value is a boolean and never undefined:
// a switch is on or off.
const model = defineModel<boolean>({ default: false });
</script>

<template>
  <div class="app-toggle" :class="{ 'app-toggle-checked': model, 'app-toggle-disabled': disabled }">
    <input
      :id="inputId"
      v-model="model"
      type="checkbox"
      class="app-toggle-input"
      role="switch"
      :disabled="disabled"
    />
    <span class="app-toggle-track">
      <span class="app-toggle-handle"></span>
    </span>
  </div>
</template>

<style scoped>
.app-toggle {
  display: inline-block;
  position: relative;
  width: 2.5rem;
  height: 1.5rem;
  flex: 0 0 auto;
}
.app-toggle-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  opacity: 0;
  z-index: 1;
  cursor: pointer;
  appearance: none;
  border-radius: 30px;
}
.app-toggle-input:disabled {
  cursor: default;
}
.app-toggle-track {
  display: block;
  width: 100%;
  height: 100%;
  border: 1px solid var(--brand-surface-300);
  border-radius: 30px;
  background: var(--brand-surface-200);
  /* The neutral flattening of Aura's form-field shadow; see AppInput. */
  box-shadow: 0 0 #0000, 0 0 #0000, 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  transition:
    background 120ms,
    border-color 120ms,
    outline-color 120ms;
  outline-color: transparent;
}
.app-toggle:not(.app-toggle-disabled):hover .app-toggle-track {
  background: var(--brand-surface-300);
  border-color: var(--brand-surface-400);
}
.app-toggle-checked .app-toggle-track {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
.app-toggle-checked:not(.app-toggle-disabled):hover .app-toggle-track {
  background: var(--brand-primary-600);
  border-color: var(--brand-primary-600);
}
.app-toggle-input:focus-visible + .app-toggle-track {
  outline: 1px solid var(--brand-red);
  outline-offset: 2px;
}
.app-toggle-handle {
  position: absolute;
  top: 50%;
  inset-inline-start: 0.25rem;
  width: 1rem;
  height: 1rem;
  margin-block-start: -0.5rem;
  border-radius: 50%;
  background: var(--brand-surface);
  transition:
    inset-inline-start 120ms,
    background 120ms;
}
.app-toggle-checked .app-toggle-handle {
  inset-inline-start: calc(100% - 1.25rem);
}
.app-toggle-disabled {
  opacity: 0.4;
}
.app-toggle-disabled .app-toggle-track {
  background: var(--brand-bg);
}
</style>
