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
  color: var(--brand-text);
  background: var(--brand-surface);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--brand-border);
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
  border-color: color-mix(in srgb, var(--brand-text-muted) 45%, transparent);
}
.app-input:enabled:focus {
  border-color: var(--brand-red);
  outline: none;
}
/* Chrome paints an autofilled field its own yellow, and refuses to let
 * ``background`` override it. An inset shadow is the only thing that
 * covers it, and the text colour has to be set through
 * ``-webkit-text-fill-color`` for the same reason. The login field is
 * the one every password manager fills. */
.app-input:-webkit-autofill,
.app-input:-webkit-autofill:hover,
.app-input:-webkit-autofill:focus,
.app-input:-webkit-autofill:active {
  box-shadow: 0 0 0 100px var(--brand-surface) inset;
  -webkit-text-fill-color: var(--brand-text);
  caret-color: var(--brand-text);
  /* Chrome animates its own yellow in when the field takes focus, and
   * the inset shadow only lands after it. A background transition it
   * never finishes is the only way to stop the flash. */
  transition: background-color 100000s ease-in-out 0s;
}
.app-input::placeholder {
  color: var(--brand-text-muted);
}
.app-input:disabled {
  opacity: 1;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
}
</style>
