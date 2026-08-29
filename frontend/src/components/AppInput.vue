<script setup lang="ts">
/**
 * The app's text input. Replaces PrimeVue's ``InputText``, across 31
 * call sites.
 *
 * Values are Aura's form-field roles resolved through
 * ``primevue-preset.ts``, which overrode four of them: the border is
 * ``surface.200`` rather than Aura's ``surface.300``, the text is
 * ``surface.900``, the placeholder ``surface.500``, and a disabled
 * field sits on ``surface.50`` rather than the khaki ``surface.200``.
 *
 * ``app-input`` is the root class on purpose: a few pages reach in with
 * ``:deep()`` to size the field inside their own layout.
 */
defineProps<{
  placeholder?: string;
  /** Fill the width of the row rather than sizing to content. */
  fluid?: boolean;
  type?: string;
  name?: string;
  inputmode?: "text" | "email" | "tel" | "url" | "numeric" | "decimal" | "search";
  autocomplete?: string;
  spellcheck?: boolean;
  autofocus?: boolean;
  disabled?: boolean;
}>();
const model = defineModel<string | null>();
</script>

<template>
  <input
    v-model="model"
    class="app-input"
    :class="{ 'app-input-fluid': fluid }"
    :type="type ?? 'text'"
    :name="name"
    :placeholder="placeholder"
    :inputmode="inputmode"
    :autocomplete="autocomplete"
    :spellcheck="spellcheck"
    :autofocus="autofocus"
    :disabled="disabled"
  />
</template>

<style scoped>
.app-input {
  font-family: inherit;
  font-feature-settings: inherit;
  font-size: 1rem;
  color: var(--brand-surface-900);
  background: var(--brand-surface-0);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--brand-surface-200);
  border-radius: 6px;
  /* Aura's form-field shadow, with its faintly blue black flattened to
   * a neutral one: shadows carry no brand here by rule
   * (scripts/check_brand_tokens.py), and at 5% alpha the two do not
   * differ on screen. */
  box-shadow: 0 0 #0000, 0 0 #0000, 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  transition:
    background 120ms,
    color 120ms,
    border-color 120ms,
    outline-color 120ms,
    box-shadow 120ms;
  outline-color: transparent;
  appearance: none;
}
.app-input-fluid {
  width: 100%;
}
.app-input:enabled:hover {
  border-color: var(--brand-surface-400);
}
.app-input:enabled:focus {
  border-color: var(--brand-primary-500);
  outline: none;
}
/* Chrome paints an autofilled field its own yellow, and refuses to let
 * ``background`` override it. An inset shadow is the only thing that
 * covers it, and the text colour has to be set through
 * ``-webkit-text-fill-color`` for the same reason. The login field is
 * the one every password manager fills. */
.app-input:-webkit-autofill,
.app-input:-webkit-autofill:hover,
.app-input:-webkit-autofill:focus {
  box-shadow: 0 0 0 100px var(--brand-surface-0) inset;
  -webkit-text-fill-color: var(--brand-surface-900);
  caret-color: var(--brand-surface-900);
}
.app-input::placeholder {
  color: var(--brand-surface-500);
}
.app-input:disabled {
  opacity: 1;
  background: var(--brand-surface-50);
  color: var(--brand-surface-500);
}
</style>
