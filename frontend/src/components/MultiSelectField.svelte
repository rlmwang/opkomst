<script lang="ts" generics="T, V">
/**
 * The app's multiple-choice list. Replaces PrimeVue's ``MultiSelect``
 * on the two pages that pick chapters: the dashboard's first-run panel
 * and the admin user editor.
 *
 * Same field, same panel and same keyboard as ``SelectField``. What
 * differs is that the model is an array, a row stays chosen rather than
 * closing the list, every row carries a checkbox, and with
 * ``display="chip"`` the chosen ones show as removable chips in the
 * field.
 */
import { tick, type Snippet } from "svelte";

import { t } from "@/i18n.svelte";
import { scrollRowIntoView, portalTarget } from "@/composables/overlay-panel";
import { useOverlayPanel } from "@/composables/useOverlayPanel.svelte";
import "@/assets/overlay-list.css";

let {
  value = $bindable(),
  options,
  optionLabel,
  optionValue,
  placeholder,
  disabled,
  filter,
  filterPlaceholder,
  display,
  fluid,
  optionSnippet,
}: {
  value?: V[];
  options?: readonly T[];
  optionLabel?: string;
  optionValue?: string;
  placeholder?: string;
  disabled?: boolean;
  filter?: boolean;
  filterPlaceholder?: string;
  /** ``chip`` shows the chosen options as chips; anything else joins
   *  their labels with commas. */
  display?: "comma" | "chip";
  fluid?: boolean;
  optionSnippet?: Snippet<[{ option: T; index: number }]>;
} = $props();

const uid = $props.id();
const listId = `${uid}-list`;
const optionId = (i: number) => `${uid}-opt-${i}`;

// Held whole, not destructured: every field is a getter.
const overlay = useOverlayPanel();

let filterInput = $state<HTMLInputElement>();
let listEl = $state<HTMLElement>();
let query = $state("");
let focusIndex = $state(-1);

function labelOf(option: T): string {
  if (optionLabel && option !== null && typeof option === "object") {
    return String((option as Record<string, unknown>)[optionLabel] ?? "");
  }
  return String(option ?? "");
}
function valueOf(option: T): V {
  if (optionValue && option !== null && typeof option === "object") {
    return (option as Record<string, unknown>)[optionValue] as V;
  }
  return option as unknown as V;
}

const allOptions = $derived(options ?? []);
const visibleOptions = $derived.by(() => {
  if (!filter || !query.trim()) return allOptions;
  const q = query.trim().toLowerCase();
  return allOptions.filter((o) => labelOf(o).toLowerCase().includes(q));
});

const picked = $derived(value ?? []);
function isPicked(option: T): boolean {
  return picked.includes(valueOf(option));
}
/** The chosen options, in the order the caller's array holds them. */
const pickedOptions = $derived(
  picked
    .map((v) => allOptions.find((o) => valueOf(o) === v))
    .filter((o): o is T => o !== undefined),
);
const summary = $derived(pickedOptions.map(labelOf).join(", "));

function show(): void {
  if (disabled || overlay.open) return;
  query = "";
  // Opening lands on the first row, so a single arrow press already has
  // somewhere to go.
  focusIndex = 0;
  overlay.show();
  void tick().then(() => filterInput?.focus({ preventScroll: true }));
}

function close(refocus = true): void {
  if (!overlay.open) return;
  overlay.hide();
  if (refocus) overlay.anchor?.focus({ preventScroll: true });
}

/** The field owns its click.

 *  A ``<label>`` around it, which is how every caption on these pages
 *  is written, forwards a click to the first labelable element in its
 *  subtree. A combobox div is not one; a chip's remove button and the
 *  clear cross are. So clicking the field to open it dropped the first
 *  chip instead, and with one chapter picked that emptied the field on
 *  the first click. Preventing the default stops that second,
 *  synthetic click at its source. */
function toggleOpen(event?: MouseEvent): void {
  event?.preventDefault();
  if (overlay.open) close();
  else show();
}

/** Choosing a row adds it; choosing it again takes it away. */
function toggleOption(option: T): void {
  const v = valueOf(option);
  value = picked.includes(v) ? picked.filter((x) => x !== v) : [...picked, v];
}

function removeAt(index: number): void {
  value = picked.filter((_, i) => i !== index);
}

function scrollFocusedIntoView(): void {
  scrollRowIntoView(listEl, focusIndex);
}

function moveFocus(to: number): void {
  const n = visibleOptions.length;
  if (n === 0) return;
  focusIndex = ((to % n) + n) % n;
  void tick().then(scrollFocusedIntoView);
}

let typed = "";
let typedTimer: ReturnType<typeof setTimeout> | undefined;
function typeAhead(char: string): void {
  typed += char.toLowerCase();
  clearTimeout(typedTimer);
  typedTimer = setTimeout(() => {
    typed = "";
  }, 500);
  const i = visibleOptions.findIndex((o) => labelOf(o).toLowerCase().startsWith(typed));
  if (i >= 0) moveFocus(i);
}

function onKeydown(event: KeyboardEvent): void {
  if (disabled) return;
  switch (event.key) {
    case "ArrowDown":
      event.preventDefault();
      if (!overlay.open) show();
      else moveFocus(focusIndex + 1);
      return;
    case "ArrowUp":
      event.preventDefault();
      if (!overlay.open) show();
      else moveFocus(focusIndex - 1);
      return;
    case "Home":
      if (!overlay.open) return;
      event.preventDefault();
      moveFocus(0);
      return;
    case "End":
      if (!overlay.open) return;
      event.preventDefault();
      moveFocus(visibleOptions.length - 1);
      return;
    case "Enter":
      event.preventDefault();
      if (!overlay.open) {
        show();
        return;
      }
      if (focusIndex < 0 && filter) moveFocus(0);
      if (visibleOptions[focusIndex]) toggleOption(visibleOptions[focusIndex]);
      return;
    case " ":
      if (filter && overlay.open) return;
      event.preventDefault();
      if (!overlay.open) show();
      else if (visibleOptions[focusIndex]) toggleOption(visibleOptions[focusIndex]);
      return;
    case "Tab":
      close(false);
      return;
    default:
      if (!filter && overlay.open && event.key.length === 1 && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        typeAhead(event.key);
      }
  }
}

$effect(() => {
  void query;
  focusIndex = -1;
  void tick().then(overlay.place);
});
// Chips wrap, so the field grows as they are added and the panel has to
// follow it down the page.
$effect(() => {
  void picked;
  void tick().then(overlay.place);
});

/** The composable hands back a style object; an element wants a string. */
function styleOf(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}: ${v}`)
    .join("; ");
}

function portal(node: HTMLElement) {
  portalTarget(overlay.anchor).appendChild(node);
  return {
    destroy() {
      node.remove();
    },
  };
}
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  bind:this={overlay.anchor}
  class="ovl-field ms-field"
  class:ovl-field-fluid={fluid}
  class:ovl-field-open={overlay.open}
  class:ovl-field-disabled={disabled}
  role="combobox"
  tabindex={disabled ? -1 : 0}
  aria-expanded={overlay.open}
  aria-controls={listId}
  aria-haspopup="listbox"
  aria-disabled={disabled || undefined}
  aria-activedescendant={overlay.open && focusIndex >= 0 ? optionId(focusIndex) : undefined}
  onclick={toggleOpen}
  onkeydown={onKeydown}
>
  <span
    class="ovl-value"
    class:ovl-value-placeholder={picked.length === 0}
    class:ms-value-chips={display === "chip"}
  >
    {#if picked.length === 0}
      {placeholder ?? ""}&nbsp;
    {:else if display === "chip"}
      {#each pickedOptions as option, i (i)}
        <span class="ms-chip">
          {labelOf(option)}
          <button
            type="button"
            class="ms-chip-remove"
            aria-label={t("common.remove")}
            onclick={(e) => {
              e.stopPropagation();
              removeAt(i);
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </span>
      {/each}
    {:else}
      {summary}
    {/if}
  </span>

  <span class="ovl-toggle" aria-hidden="true">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6" /></svg>
  </span>

  {#if overlay.open}
    <div use:portal style="display: contents">
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        bind:this={overlay.panel}
        class="ovl-panel"
        style={styleOf(overlay.style)}
        onkeydown={onKeydown}
      >
        {#if filter}
          <div class="ovl-header">
            <input
              bind:this={filterInput}
              bind:value={query}
              type="text"
              class="ovl-filter"
              placeholder={filterPlaceholder}
              autocomplete="off"
            />
          </div>
        {/if}
        <div class="ovl-list-container">
          <ul id={listId} bind:this={listEl} class="ovl-list" role="listbox" aria-multiselectable="true">
            {#each visibleOptions as option, i (i)}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <li
                id={optionId(i)}
                class="ovl-option"
                class:ovl-option-focus={i === focusIndex}
                class:ovl-option-selected={isPicked(option)}
                role="option"
                aria-selected={isPicked(option)}
                onclick={() => toggleOption(option)}
                onmousemove={() => (focusIndex = i)}
              >
                <span class="ms-box" class:ms-box-on={isPicked(option)} aria-hidden="true">
                  {#if isPicked(option)}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                  {/if}
                </span>
                {#if optionSnippet}
                  {@render optionSnippet({ option, index: i })}
                {:else}
                  {labelOf(option)}
                {/if}
              </li>
            {/each}
            {#if visibleOptions.length === 0}
              <li class="ovl-empty" role="option" aria-selected="false" aria-disabled="true">
                {t("common.noResults")}
              </li>
            {/if}
          </ul>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
/* Chips wrap onto a second line rather than making the field scroll
 * sideways, which is what a chapter list with six picks needs. The
 * chevron is not one of them: aligning the row to the top left it
 * pinned to the field's top edge at the height of its own icon, which
 * reads as a tiny arrow in the wrong place. It centres on the first
 * line of chips, where the eye expects it whether there is one row of
 * them or three. */
.ms-field {
  align-items: flex-start;
}
.ms-field :global(.ovl-toggle) {
  align-self: center;
}
.ms-value-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  white-space: normal;
  overflow: visible;
}
.ms-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  background: var(--brand-border);
  color: var(--brand-text);
  border-radius: 4px;
  padding: 0.125rem 0.5rem;
  font-size: 0.875rem;
}
.ms-chip-remove {
  display: inline-flex;
  align-items: center;
  border: 0 none;
  background: transparent;
  padding: 0;
  color: inherit;
  cursor: pointer;
  border-radius: 999px;
}
.ms-chip-remove:hover {
  background: color-mix(in srgb, var(--brand-text-muted) 25%, transparent);
}

/* The checkbox in front of each row. The panel is moved to the body, so
 * this cannot be scoped to the component. Aura's checkbox geometry: a
 * 20px square with a 4px radius that fills with the accent when on. */

/* The checkbox in front of each row. The panel is teleported, so this
 * cannot be scoped. Aura's checkbox geometry: a 20px square with a 4px
 * radius that fills with the accent when it is on. */
:global(.ovl-option .ms-box) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: 1px solid var(--brand-border);
  border-radius: 4px;
  background: var(--brand-surface);
  color: #fff;
}
:global(.ovl-option .ms-box-on) {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
</style>
