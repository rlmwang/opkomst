<script setup lang="ts">
/**
 * The app's multi-line input. Same values as ``AppInput``, plus the one
 * thing a textarea does that an input does not: grow to fit what has
 * been typed into it, when the caller asks.
 *
 * The root element is the ``<textarea>`` itself, so a caller holding a
 * template ref reaches the real field through ``$el`` and can read
 * ``selectionStart`` on it. ``AdminWhatsAppPage`` inserts emoji at the
 * caret that way.
 */
import { nextTick, onMounted, ref, watch } from "vue";

const props = defineProps<{
  placeholder?: string;
  rows?: number;
  maxlength?: number;
  disabled?: boolean;
  fluid?: boolean;
  autoResize?: boolean;
}>();
const model = defineModel<string | null>();
const field = ref<HTMLTextAreaElement>();

function fit(): void {
  const el = field.value;
  if (!el || !props.autoResize) return;
  // Collapse first, or the field can only ever grow.
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

onMounted(() => {
  if (props.autoResize) nextTick(fit);
});
watch(model, () => {
  if (props.autoResize) nextTick(fit);
});
</script>

<template>
  <textarea
    ref="field"
    v-model="model"
    class="app-textarea"
    :class="{ 'app-textarea-fluid': fluid, 'app-textarea-auto': autoResize }"
    :rows="rows"
    :placeholder="placeholder"
    :maxlength="maxlength"
    :disabled="disabled"
    @input="fit"
  ></textarea>
</template>

<style scoped>
.app-textarea {
  font-family: inherit;
  font-feature-settings: inherit;
  font-size: 1rem;
  color: var(--brand-surface-900);
  background: var(--brand-surface-0);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--brand-surface-200);
  border-radius: 6px;
  /* The neutral flattening of Aura's form-field shadow; see AppInput. */
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
.app-textarea-fluid {
  width: 100%;
}
/* A field that sizes itself must not also be draggable, or the two
 * fight and the drag is undone on the next keystroke. */
.app-textarea-auto {
  resize: none;
  overflow: hidden;
}
.app-textarea:enabled:hover {
  border-color: var(--brand-surface-400);
}
.app-textarea:enabled:focus {
  border-color: var(--brand-primary-500);
  outline: none;
}
/* Chrome paints an autofilled field its own yellow, and refuses to let
 * ``background`` override it. An inset shadow is the only thing that
 * covers it, and the text colour has to be set through
 * ``-webkit-text-fill-color`` for the same reason. The login field is
 * the one every password manager fills. */
.app-textarea:-webkit-autofill,
.app-textarea:-webkit-autofill:hover,
.app-textarea:-webkit-autofill:focus {
  box-shadow: 0 0 0 100px var(--brand-surface-0) inset;
  -webkit-text-fill-color: var(--brand-surface-900);
  caret-color: var(--brand-surface-900);
}
.app-textarea::placeholder {
  color: var(--brand-surface-500);
}
.app-textarea:disabled {
  opacity: 1;
  background: var(--brand-surface-50);
  color: var(--brand-surface-500);
}
</style>
