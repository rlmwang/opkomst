<script lang="ts">
/**
 * Brand-styled single-select dropdown for the public mini-app.
 *
 * Native ``<select>`` works for input, but its open panel is
 * rendered by the OS — Chrome/Firefox/Safari all show their own
 * non-themable list, which made the public form look stylistically
 * adrift from the rest of the cream/red brand. The organiser app's own
 * ``SelectField`` draws a fully-themed panel; this is the mini-app's
 * equivalent, without its i18n or its overlay composable.
 *
 * This is a minimal accessible re-implementation: button trigger
 * + floating listbox + arrow / enter / escape key handling +
 * click-outside-to-close. ~80 LOC, no extra deps.
 */
import { onMount, tick } from "svelte";

let {
  value = $bindable(),
  options,
  placeholder,
  disabled,
  ariaLabel,
}: {
  value: string | null;
  options: readonly string[];
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
} = $props();

let open = $state(false);
let root = $state<HTMLElement | null>(null);
let listEl = $state<HTMLElement | null>(null);
// "Active descendant": the keyboard-highlighted option, separate from
// the committed value. Reset to the current selection when opened.
let activeIndex = $state(-1);

// ``items`` includes the placeholder as the first row so visitors can
// re-pick it to clear, the same affordance as a re-clickable disabled
// option in a native select.
interface Item {
  value: string | null;
  label: string;
}
const items = $derived<Item[]>([
  { value: null, label: placeholder ?? "" },
  ...options.map((o) => ({ value: o, label: o })),
]);

const selectedLabel = $derived.by(() => {
  const item = items.find((i) => i.value === value);
  return item ? item.label : (placeholder ?? "");
});
const isPlaceholder = $derived(value === null);

function toggle() {
  if (disabled) return;
  open = !open;
  if (open) {
    activeIndex = items.findIndex((i) => i.value === value);
    if (activeIndex < 0) activeIndex = 0;
    void tick().then(scrollActiveIntoView);
  }
}
function close() {
  open = false;
}
function pick(item: Item) {
  value = item.value;
  open = false;
}
function onKeydown(ev: KeyboardEvent) {
  if (disabled) return;
  if (!open) {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(ev.key)) {
      ev.preventDefault();
      toggle();
    }
    return;
  }
  if (ev.key === "Escape") {
    ev.preventDefault();
    close();
    return;
  }
  if (ev.key === "Enter" || ev.key === " ") {
    ev.preventDefault();
    if (activeIndex >= 0) pick(items[activeIndex]);
    return;
  }
  if (ev.key === "ArrowDown") {
    ev.preventDefault();
    activeIndex = Math.min(items.length - 1, activeIndex + 1);
    void tick().then(scrollActiveIntoView);
  }
  if (ev.key === "ArrowUp") {
    ev.preventDefault();
    activeIndex = Math.max(0, activeIndex - 1);
    void tick().then(scrollActiveIntoView);
  }
  if (ev.key === "Home") {
    ev.preventDefault();
    activeIndex = 0;
    void tick().then(scrollActiveIntoView);
  }
  if (ev.key === "End") {
    ev.preventDefault();
    activeIndex = items.length - 1;
    void tick().then(scrollActiveIntoView);
  }
}
function scrollActiveIntoView() {
  const el = listEl?.children[activeIndex] as HTMLElement | undefined;
  el?.scrollIntoView({ block: "nearest" });
}

// Click-outside dismiss.
function onDocClick(ev: MouseEvent) {
  if (!open) return;
  const node = ev.target as Node | null;
  if (root && node && !root.contains(node)) close();
}
onMount(() => {
  document.addEventListener("click", onDocClick);
  return () => document.removeEventListener("click", onDocClick);
});

// If the field is disabled while it is open (event data resets, and so
// on), close the panel.
$effect(() => {
  if (disabled) close();
});

const triggerId = `branded-select-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div bind:this={root} class="branded-select" class:open class:disabled>
  <button
    id={triggerId}
    type="button"
    class="trigger input"
    {disabled}
    aria-haspopup="listbox"
    aria-expanded={open}
    aria-label={ariaLabel}
    onclick={toggle}
    onkeydown={onKeydown}
  >
    <span class="trigger-label" class:placeholder={isPlaceholder}>
      {selectedLabel}
    </span>
    <span class="chevron" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
    </span>
  </button>
  {#if open}
    <ul bind:this={listEl} class="listbox" role="listbox" aria-labelledby={triggerId} tabindex="-1">
      {#each items as item, i (i)}
        <li
          class="option"
          class:active={i === activeIndex}
          class:selected={item.value === value}
          class:is-placeholder={item.value === null}
          role="option"
          aria-selected={item.value === value}
          onmousedown={(e) => {
            e.preventDefault();
            pick(item);
          }}
          onmouseenter={() => (activeIndex = i)}
        >
          <span class="option-label">{item.label}</span>
          {#if item.value === value && item.value !== null}
            <svg
              class="option-check"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            ><polyline points="20 6 9 17 4 12"/></svg>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
.branded-select {
  position: relative;
  width: 100%;
}

.trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  text-align: left;
  font: inherit;
  font-size: 16px;
  padding: 0.625rem 0.75rem;
  background: var(--brand-bg);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  width: 100%;
  cursor: pointer;
}
.trigger:focus-visible {
  outline: none;
  border-color: var(--brand-red);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-red) 18%, transparent);
}
.trigger:disabled { cursor: default; opacity: 0.6; }
.branded-select.open .trigger { border-color: var(--brand-red); }

.trigger-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.trigger-label.placeholder { color: var(--brand-text-muted); }

.chevron {
  display: inline-flex;
  align-items: center;
  color: var(--brand-red);
  transition: transform 120ms ease;
  flex-shrink: 0;
}
.branded-select.open .chevron { transform: rotate(180deg); }

.listbox {
  position: absolute;
  z-index: 10;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
  max-height: 16rem;
  overflow-y: auto;
}

.option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.95rem;
  line-height: 1.3;
  color: var(--brand-text);
}
.option.is-placeholder { color: var(--brand-text-muted); }
.option.active {
  background: color-mix(in srgb, var(--brand-red) 8%, var(--brand-bg));
}
.option.selected {
  background: color-mix(in srgb, var(--brand-red) 14%, var(--brand-bg));
  font-weight: 600;
}
.option-check {
  color: var(--brand-red);
  flex-shrink: 0;
}
</style>
