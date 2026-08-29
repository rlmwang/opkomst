<script lang="ts" generics="T, V">
/**
 * The app's single-choice list. Replaces PrimeVue's ``Select``.
 *
 * The prop names are PrimeVue's, so a call site changes its import and
 * nothing else: ``options``, ``optionLabel``, ``optionValue``,
 * ``placeholder``, ``disabled``, ``filter``, ``filterPlaceholder``,
 * ``showClear``, ``fluid``, and the ``value`` and ``option`` snippets.
 *
 * The keyboard is the part worth reading. The field is an ARIA
 * combobox: the arrows open the list and walk it, Home and End jump to
 * the ends, typing a few letters jumps to the row that starts with
 * them, Enter takes the focused row, Escape closes and hands focus
 * back. Nothing is chosen by moving over it, so a keyboard user can
 * look before picking.
 *
 * Placement, the move to the body and dismissal come from
 * ``composables/useOverlayPanel``; the panel and row styling from
 * ``assets/overlay-list.css``. Both are shared with the multi-select
 * and the autocomplete.
 */
import { tick, type Snippet } from "svelte";

import { t } from "@/i18n.svelte";
import { scrollRowIntoView } from "@/composables/overlay-panel";
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
  showClear,
  fluid,
  class: className,
  valueSnippet,
  optionSnippet,
}: {
  value?: V;
  options?: readonly T[];
  /** Field on the option holding its text. Omitted means the option is its own text. */
  optionLabel?: string;
  /** Field on the option holding the value. Omitted means the option itself is the value. */
  optionValue?: string;
  placeholder?: string;
  disabled?: boolean;
  /** Show a filter box above the list. */
  filter?: boolean;
  filterPlaceholder?: string;
  /** Show a cross that empties the field. */
  showClear?: boolean;
  fluid?: boolean;
  class?: string;
  valueSnippet?: Snippet<[{ value: V | undefined; placeholder: string | undefined }]>;
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

// --- reading an option ----------------------------------------------
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

const selectedOption = $derived(allOptions.find((o) => valueOf(o) === value));
// A value with no matching option still counts as filled, so the
// placeholder does not reappear under a value the caller set.
const hasValue = $derived(value !== null && value !== undefined);
const displayLabel = $derived(selectedOption ? labelOf(selectedOption) : "");

// --- opening and closing ---------------------------------------------
function show(): void {
  if (disabled || overlay.open) return;
  query = "";
  // Opening lands on the chosen row, or on the first one when nothing
  // is chosen, so a single arrow press already has somewhere to go.
  const chosen = visibleOptions.findIndex((o) => valueOf(o) === value);
  focusIndex = chosen >= 0 ? chosen : 0;
  overlay.show();
  void tick().then(() => {
    filterInput?.focus({ preventScroll: true });
    scrollFocusedIntoView();
  });
}

function close(refocus = true): void {
  if (!overlay.open) return;
  overlay.hide();
  if (refocus) overlay.anchor?.focus({ preventScroll: true });
}

function toggleOpen(): void {
  if (overlay.open) close();
  else show();
}

// --- choosing ---------------------------------------------------------
function choose(option: T): void {
  value = valueOf(option);
  close();
}

function clear(): void {
  value = null as V;
}

// --- the keyboard -----------------------------------------------------
function scrollFocusedIntoView(): void {
  scrollRowIntoView(listEl, focusIndex);
}

function moveFocus(to: number): void {
  const n = visibleOptions.length;
  if (n === 0) return;
  focusIndex = ((to % n) + n) % n;
  void tick().then(scrollFocusedIntoView);
}

// Typing letters with the list open jumps to the row that starts with
// them. Only when there is no filter box: with one, the letters belong
// in it.
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
      // With a filter box and nothing walked to, Enter takes the first
      // row the filter left standing.
      if (focusIndex < 0 && filter) moveFocus(0);
      if (visibleOptions[focusIndex]) choose(visibleOptions[focusIndex]);
      return;
    case " ":
      // The filter box owns the space bar while it has focus.
      if (filter && overlay.open) return;
      event.preventDefault();
      if (!overlay.open) show();
      else if (visibleOptions[focusIndex]) choose(visibleOptions[focusIndex]);
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

// Filtering changes the list under the roving focus, so the focus goes
// back to the top of what is left. The panel is also re-measured: a
// shorter list may now fit below the field.
$effect(() => {
  void query;
  focusIndex = -1;
  void tick().then(overlay.place);
});

/** The composable hands back a style object; an element wants a string. */
function styleOf(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}: ${v}`)
    .join("; ");
}

function portal(node: HTMLElement) {
  document.body.appendChild(node);
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
  class="ovl-field {className ?? ''}"
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
  <span class="ovl-value" class:ovl-value-placeholder={!hasValue}>
    {#if valueSnippet}
      {@render valueSnippet({ value, placeholder })}
    {:else}
      {hasValue ? displayLabel : (placeholder ?? "")}
    {/if}
    {#if !hasValue && !placeholder}&nbsp;{/if}
  </span>

  {#if showClear && hasValue && !disabled}
    <button
      type="button"
      class="ovl-clear"
      aria-label={t("common.clear")}
      onclick={(e) => {
        e.stopPropagation();
        clear();
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12" /></svg>
    </button>
  {/if}
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
          <ul id={listId} bind:this={listEl} class="ovl-list" role="listbox">
            {#each visibleOptions as option, i (i)}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <li
                id={optionId(i)}
                class="ovl-option"
                class:ovl-option-focus={i === focusIndex}
                class:ovl-option-selected={valueOf(option) === value}
                role="option"
                aria-selected={valueOf(option) === value}
                onclick={() => choose(option)}
                onmousemove={() => (focusIndex = i)}
              >
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
