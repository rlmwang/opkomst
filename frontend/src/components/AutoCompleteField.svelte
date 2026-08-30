<script lang="ts" module>
/** What the field hands to ``oncomplete``: the text typed so far. */
export interface AutoCompleteCompleteEvent {
  originalEvent: Event;
  query: string;
}
/** What the field hands to ``onoptionSelect``: the suggestion picked. */
export interface AutoCompleteOptionSelectEvent {
  originalEvent: Event;
  value: unknown;
}
</script>

<script lang="ts" generics="T">
/**
 * The app's type-and-pick field. Replaces PrimeVue's ``AutoComplete``
 * in the chapter, city and address pickers.
 *
 * The list arrives from the caller rather than from a fixed set: typing
 * waits ``delay`` milliseconds and then emits ``complete`` with the
 * text, and the caller answers by filling ``suggestions``. The model is
 * the typed string until a suggestion is taken, and the suggestion
 * itself afterwards, which is the distinction ``ChapterPicker`` reads
 * to tell "pick this one" from "make a new one".
 *
 * Panel, list and keyboard are ``SelectField``'s, so all three overlay
 * fields walk the same way.
 */
import { tick, type Snippet } from "svelte";

import { t } from "@/i18n.svelte";
import { scrollRowIntoView, portalTarget } from "@/composables/overlay-panel";
import { useOverlayPanel } from "@/composables/useOverlayPanel.svelte";
import "@/assets/overlay-list.css";

let {
  value = $bindable(),
  suggestions,
  optionLabel,
  placeholder,
  disabled,
  delay = 300,
  minLength = 1,
  fluid,
  class: className,
  optionSnippet,
  oncomplete,
  onoptionSelect,
  onblur,
  onkeyup,
}: {
  value?: unknown;
  suggestions?: readonly T[];
  optionLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  /** Milliseconds of quiet typing before ``oncomplete`` fires. */
  delay?: number;
  /** Shortest text worth asking about. */
  minLength?: number;
  fluid?: boolean;
  class?: string;
  optionSnippet?: Snippet<[{ option: T; index: number }]>;
  oncomplete?: (event: AutoCompleteCompleteEvent) => void;
  onoptionSelect?: (event: AutoCompleteOptionSelectEvent) => void;
  onblur?: (event: FocusEvent) => void;
  onkeyup?: (event: KeyboardEvent) => void;
} = $props();

const uid = $props.id();
const listId = `${uid}-list`;
const optionId = (i: number) => `${uid}-opt-${i}`;

// Held whole, not destructured: every field is a getter.
const overlay = useOverlayPanel({
  onEscape: () => {
    typing = false;
    input?.focus({ preventScroll: true });
  },
});

let input = $state<HTMLInputElement>();
let listEl = $state<HTMLElement>();
let focusIndex = $state(-1);
// True from the first keystroke until the field is left or a suggestion
// taken. A list that arrives after the user has stopped typing should
// not reopen the panel behind their back.
let typing = $state(false);

function labelOf(option: T): string {
  if (optionLabel && option !== null && typeof option === "object") {
    return String((option as Record<string, unknown>)[optionLabel] ?? "");
  }
  return String(option ?? "");
}

const items = $derived(suggestions ?? []);

/** The model is a string while typing and an option once one is taken. */
const text = $derived.by(() => {
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? labelOf(value as T) : String(value);
});

let timer: ReturnType<typeof setTimeout> | undefined;

function onInput(event: Event): void {
  const typedText = (event.currentTarget as HTMLInputElement).value;
  value = typedText;
  clearTimeout(timer);
  if (typedText.length < minLength) {
    typing = false;
    overlay.hide();
    return;
  }
  typing = true;
  timer = setTimeout(() => {
    oncomplete?.({ originalEvent: event, query: typedText });
  }, delay);
}

// The caller answers ``complete`` by filling ``suggestions``. Showing
// the panel is this side's job, so the pickers stay declarative.
$effect(() => {
  const list = items;
  focusIndex = -1;
  if (!typing || list.length === 0) {
    overlay.hide();
    return;
  }
  if (overlay.open) void tick().then(overlay.place);
  else overlay.show();
});

function choose(option: T, event: Event): void {
  value = option;
  onoptionSelect?.({ originalEvent: event, value: option });
  typing = false;
  overlay.hide();
  input?.focus({ preventScroll: true });
}

function scrollFocusedIntoView(): void {
  scrollRowIntoView(listEl, focusIndex);
}

function moveFocus(to: number): void {
  const n = items.length;
  if (n === 0) return;
  focusIndex = ((to % n) + n) % n;
  void tick().then(scrollFocusedIntoView);
}

function onKeydown(event: KeyboardEvent): void {
  switch (event.key) {
    case "ArrowDown":
      if (!overlay.open) return;
      event.preventDefault();
      moveFocus(focusIndex + 1);
      return;
    case "ArrowUp":
      if (!overlay.open) return;
      event.preventDefault();
      moveFocus(focusIndex - 1);
      return;
    case "Home":
      if (!overlay.open || focusIndex < 0) return;
      event.preventDefault();
      moveFocus(0);
      return;
    case "End":
      if (!overlay.open || focusIndex < 0) return;
      event.preventDefault();
      moveFocus(items.length - 1);
      return;
    case "Enter":
      if (!overlay.open) return;
      // Enter with nothing walked to leaves the text alone and closes
      // the list, so a caller that treats Enter as "make a new one"
      // still hears it.
      if (focusIndex >= 0 && items[focusIndex]) {
        event.preventDefault();
        choose(items[focusIndex], event);
      } else {
        typing = false;
        overlay.hide();
      }
      return;
    case "Tab":
      typing = false;
      overlay.hide();
  }
}

function onBlur(event: FocusEvent): void {
  typing = false;
  onblur?.(event);
}

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

<div bind:this={overlay.anchor} class="ac {className ?? ''}" class:ac-fluid={fluid}>
  <input
    bind:this={input}
    type="text"
    class="ac-input"
    class:ac-input-fluid={fluid}
    value={text}
    {placeholder}
    {disabled}
    role="combobox"
    aria-expanded={overlay.open}
    aria-controls={listId}
    aria-autocomplete="list"
    aria-activedescendant={overlay.open && focusIndex >= 0 ? optionId(focusIndex) : undefined}
    autocomplete="off"
    oninput={onInput}
    onkeydown={onKeydown}
    onblur={onBlur}
    {onkeyup}
  />

  <!-- ``mousedown.prevent`` keeps focus in the input while a suggestion
       is clicked, so the caller's ``onblur`` does not run before the
       pick it was about to see. -->
  {#if overlay.open}
    <div use:portal style="display: contents">
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        bind:this={overlay.panel}
        class="ovl-panel"
        style={styleOf(overlay.style)}
        onmousedown={(e) => e.preventDefault()}
      >
        <div class="ovl-list-container">
          <ul id={listId} bind:this={listEl} class="ovl-list" role="listbox">
            {#each items as option, i (i)}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <li
                id={optionId(i)}
                class="ovl-option"
                class:ovl-option-focus={i === focusIndex}
                role="option"
                aria-selected={i === focusIndex}
                onclick={(e) => choose(option, e)}
                onmousemove={() => (focusIndex = i)}
              >
                {#if optionSnippet}
                  {@render optionSnippet({ option, index: i })}
                {:else}
                  {labelOf(option)}
                {/if}
              </li>
            {/each}
            {#if items.length === 0}
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
.ac {
  display: inline-flex;
  max-width: 100%;
}
.ac-fluid {
  display: flex;
}
/* The same field as ``AppInput``: this one sits beside plain text
 * inputs in every form that uses it. */
.ac-input {
  flex: 1 1 auto;
  width: 1%;
  font-family: inherit;
  font-feature-settings: inherit;
  font-size: 1rem;
  color: var(--brand-text);
  background: var(--brand-surface);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
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
.ac-input:enabled:hover {
  border-color: color-mix(in srgb, var(--brand-text-muted) 45%, transparent);
}
.ac-input:enabled:focus {
  border-color: var(--brand-red);
  outline: none;
}
.ac-input::placeholder {
  color: var(--brand-text-muted);
}
.ac-input:disabled {
  opacity: 1;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
}
</style>
