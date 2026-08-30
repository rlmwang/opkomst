<script lang="ts">
/**
 * The app's multi-line input. Same values as ``AppInput``, plus the one
 * thing a textarea does that an input does not: grow to fit what has
 * been typed into it, when the caller asks.
 *
 * ``element`` hands the real ``<textarea>`` back to a caller that needs
 * the caret. ``AdminWhatsAppPage`` reads ``selectionStart`` off it to
 * insert an emoji where the cursor is.
 */
let {
  value = $bindable(),
  placeholder,
  rows,
  maxlength,
  disabled,
  fluid,
  autoResize,
  element = $bindable(),
  class: className,
}: {
  value?: string | null;
  placeholder?: string;
  rows?: number;
  maxlength?: number;
  disabled?: boolean;
  fluid?: boolean;
  autoResize?: boolean;
  /** The field itself, for a caller that needs the caret. */
  element?: HTMLTextAreaElement;
  class?: string;
} = $props();

let field = $state<HTMLTextAreaElement>();

$effect(() => {
  element = field;
});

function fit(): void {
  if (!field || !autoResize) return;
  // Collapse first, or the field can only ever grow.
  field.style.height = "auto";
  field.style.height = `${field.scrollHeight}px`;
}

// Reads the value, so a change from anywhere resizes it: the mount, a
// prefill arriving from the server, or a revert.
$effect(() => {
  void value;
  if (autoResize) fit();
});
</script>

<textarea
  bind:this={field}
  bind:value
  class="app-textarea {className ?? ''}"
  class:app-textarea-fluid={fluid}
  class:app-textarea-auto={autoResize}
  {rows}
  {placeholder}
  {maxlength}
  {disabled}
  oninput={fit}
></textarea>

<style>
.app-textarea {
  font-family: inherit;
  font-feature-settings: inherit;
  font-size: 1rem;
  color: var(--brand-text);
  background: var(--brand-surface);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--brand-border);
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
  border-color: color-mix(in srgb, var(--brand-text-muted) 45%, transparent);
}
.app-textarea:enabled:focus {
  border-color: var(--brand-red);
  outline: none;
}
/* Chrome paints an autofilled field its own yellow, and refuses to let
 * ``background`` override it. An inset shadow is the only thing that
 * covers it, and the text colour has to be set through
 * ``-webkit-text-fill-color`` for the same reason. The login field is
 * the one every password manager fills. */
.app-textarea:-webkit-autofill,
.app-textarea:-webkit-autofill:hover,
.app-textarea:-webkit-autofill:focus,
.app-textarea:-webkit-autofill:active {
  box-shadow: 0 0 0 100px var(--brand-surface) inset;
  -webkit-text-fill-color: var(--brand-text);
  caret-color: var(--brand-text);
  /* Chrome animates its own yellow in when the field takes focus, and
   * the inset shadow only lands after it. A background transition it
   * never finishes is the only way to stop the flash. */
  transition: background-color 100000s ease-in-out 0s;
}
.app-textarea::placeholder {
  color: var(--brand-text-muted);
}
.app-textarea:disabled {
  opacity: 1;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
}
</style>
