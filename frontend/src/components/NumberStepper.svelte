<script lang="ts">
/**
 * Integer counter with a centered value and joined − / + buttons. The
 * app-wide counter control, ported from the public event sign-up's
 * attendee stepper so every counter (party size, cycle weeks, people
 * per shift, reminder days) looks identical. Clamps to [min, max];
 * blocks non-digit input; empties gracefully mid-edit and normalises on
 * blur.
 */
let {
  value = $bindable(),
  min = 0,
  max = 999,
  ariaLabel,
  suffix,
}: {
  value: number;
  min?: number;
  max?: number;
  ariaLabel?: string;
  /** A unit shown after the number, e.g. ``s``. Inside the field, so it
   *  scrolls and aligns with the value rather than floating beside the
   *  control. */
  suffix?: string;
} = $props();

function clamp(n: number): number {
  return Math.min(max, Math.max(min, n));
}

function step(delta: number): void {
  value = clamp((value || 0) + delta);
}

// Block anything that isn't a digit so the field can't show junk: a
// letter or a period just does nothing.
function onBeforeInput(ev: InputEvent): void {
  if (ev.data != null && /\D/.test(ev.data)) ev.preventDefault();
}

function onInput(ev: Event): void {
  const raw = (ev.currentTarget as HTMLInputElement).value;
  if (raw === "") return; // mid-edit blank, wait for blur
  const n = Number.parseInt(raw, 10);
  if (!Number.isNaN(n)) value = clamp(n);
}

function onBlur(ev: FocusEvent): void {
  const raw = (ev.currentTarget as HTMLInputElement).value;
  const n = raw === "" ? min : Number.parseInt(raw, 10);
  value = clamp(Number.isNaN(n) ? min : n);
}
</script>

<div class="number-field">
  <button type="button" class="num-step" aria-label="−" disabled={value <= min} onclick={() => step(-1)}
    >−</button
  >
  <input
    {value}
    type="number"
    class="num-input"
    {min}
    {max}
    step="1"
    inputmode="numeric"
    aria-label={ariaLabel}
    onbeforeinput={(e) => onBeforeInput(e as InputEvent)}
    oninput={onInput}
    onblur={(e) => onBlur(e as FocusEvent)}
  />
  {#if suffix}<span class="num-suffix">{suffix}</span>{/if}
  <button type="button" class="num-step" aria-label="+" disabled={value >= max} onclick={() => step(1)}
    >+</button
  >
</div>

<style>
/* The unit sits in the field's own box, between the value and the +
 * button, so the two read as one number. */
.num-suffix {
  display: inline-flex;
  align-items: center;
  padding-inline-end: 0.5rem;
  border-block: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text-muted);
}
/* Ported verbatim from the public event sign-up stepper so the counter
 * reads the same everywhere. Sized to its content, not fluid. */
.number-field {
  display: inline-flex;
  align-items: stretch;
  width: max-content;
}
.num-step {
  font: inherit;
  font-size: 1.125rem;
  font-weight: 600;
  line-height: 1;
  width: 2.75rem;
  flex-shrink: 0;
  background: var(--brand-bg);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  cursor: pointer;
  transition: background 120ms, border-color 120ms;
}
.num-step:first-child {
  border-radius: 6px 0 0 6px;
  border-right: 0;
}
.num-step:last-child {
  border-radius: 0 6px 6px 0;
  border-left: 0;
}
.num-step:hover:not(:disabled) {
  background: color-mix(in srgb, var(--brand-red) 10%, var(--brand-bg));
  border-color: var(--brand-red);
  position: relative;
  z-index: 1;
}
/* Dimmed but keeps the default cursor — a soft min/max bound, not a
 * forbidden action. */
.num-step:disabled {
  opacity: 0.45;
  cursor: default;
}
.num-input {
  font: inherit;
  text-align: center;
  width: 3.5rem;
  padding: 0.5rem 0.25rem;
  border: 1px solid var(--brand-border);
  border-radius: 0;
  background: var(--brand-surface);
  color: var(--brand-text);
}
/* Hide the browser-native spinner — we render our own. */
.num-input::-webkit-outer-spin-button,
.num-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.num-input {
  -moz-appearance: textfield;
  appearance: textfield;
}
</style>
