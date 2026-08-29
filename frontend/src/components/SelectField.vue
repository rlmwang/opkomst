<script setup lang="ts" generic="T, V = unknown">
/**
 * The app's single-choice list. Replaces PrimeVue's ``Select`` across
 * eight call sites.
 *
 * The prop names are PrimeVue's, so a call site changes its import and
 * nothing else: ``options``, ``optionLabel``, ``optionValue``,
 * ``placeholder``, ``disabled``, ``filter``, ``filterPlaceholder``,
 * ``showClear``, ``fluid``, and the ``value`` and ``option`` slots.
 *
 * The keyboard is the part worth reading. The field is an ARIA
 * combobox: the arrows open the list and walk it, Home and End jump to
 * the ends, typing a few letters jumps to the row that starts with
 * them, Enter takes the focused row, Escape closes and hands focus
 * back. Nothing is chosen by moving over it, so a keyboard user can
 * look before picking.
 *
 * Placement, teleporting and dismissal come from
 * ``composables/useOverlayPanel``; the panel and row styling from
 * ``assets/overlay-list.css``. Both are shared with the multi-select
 * and the autocomplete.
 */
import { computed, nextTick, ref, useId, watch } from "vue";
import { useI18n } from "@/i18n";

import { useOverlayPanel } from "@/composables/useOverlayPanel";
import "@/assets/overlay-list.css";

const props = defineProps<{
  modelValue?: V;
  options?: readonly T[];
  /** Field on the option holding its text. Omitted means the option is its own text. */
  optionLabel?: string;
  /** Field on the option holding the model value. Omitted means the option itself is the value. */
  optionValue?: string;
  placeholder?: string;
  disabled?: boolean;
  /** Show a filter box above the list. */
  filter?: boolean;
  filterPlaceholder?: string;
  /** Show a cross that empties the field. */
  showClear?: boolean;
  fluid?: boolean;
}>();

const emit = defineEmits<{ "update:modelValue": [value: V] }>();

const { t } = useI18n();

const uid = useId();
const listId = `${uid}-list`;
const optionId = (i: number) => `${uid}-opt-${i}`;

const {
  anchor: root,
  panel,
  open,
  style: panelStyle,
  show: openPanel,
  hide,
  place,
} = useOverlayPanel();

const filterInput = ref<HTMLInputElement>();
const listEl = ref<HTMLElement>();
const query = ref("");
const focusIndex = ref(-1);

// --- reading an option ----------------------------------------------
function labelOf(option: T): string {
  if (props.optionLabel && option !== null && typeof option === "object") {
    return String((option as Record<string, unknown>)[props.optionLabel] ?? "");
  }
  return String(option ?? "");
}
function valueOf(option: T): V {
  if (props.optionValue && option !== null && typeof option === "object") {
    return (option as Record<string, unknown>)[props.optionValue] as V;
  }
  return option as unknown as V;
}

const allOptions = computed(() => props.options ?? []);
const visibleOptions = computed(() => {
  if (!props.filter || !query.value.trim()) return allOptions.value;
  const q = query.value.trim().toLowerCase();
  return allOptions.value.filter((o) => labelOf(o).toLowerCase().includes(q));
});

const selectedOption = computed(() =>
  allOptions.value.find((o) => valueOf(o) === props.modelValue),
);
// A value with no matching option still counts as filled, so the
// placeholder does not reappear under a value the caller set.
const hasValue = computed(() => props.modelValue !== null && props.modelValue !== undefined);
const displayLabel = computed(() =>
  selectedOption.value ? labelOf(selectedOption.value) : "",
);

// --- opening and closing ---------------------------------------------
function show(): void {
  if (props.disabled || open.value) return;
  query.value = "";
  // Opening lands on the chosen row, or on the first one when nothing
  // is chosen, so a single arrow press already has somewhere to go.
  const chosen = visibleOptions.value.findIndex((o) => valueOf(o) === props.modelValue);
  focusIndex.value = chosen >= 0 ? chosen : 0;
  openPanel();
  void nextTick(() => {
    filterInput.value?.focus();
    scrollFocusedIntoView();
  });
}

function close(refocus = true): void {
  if (!open.value) return;
  hide();
  if (refocus) root.value?.focus();
}

function toggleOpen(): void {
  if (open.value) close();
  else show();
}

// --- choosing ---------------------------------------------------------
function choose(option: T): void {
  emit("update:modelValue", valueOf(option));
  close();
}

function clear(): void {
  emit("update:modelValue", null as V);
}

// --- the keyboard -----------------------------------------------------
function scrollFocusedIntoView(): void {
  const row = listEl.value?.children[focusIndex.value] as HTMLElement | undefined;
  row?.scrollIntoView({ block: "nearest" });
}

function moveFocus(to: number): void {
  const n = visibleOptions.value.length;
  if (n === 0) return;
  focusIndex.value = ((to % n) + n) % n;
  void nextTick(scrollFocusedIntoView);
}

// Typing letters with the list open jumps to the row that starts with
// them. Only when there is no filter box: with one, the letters belong
// in it.
const typed = ref("");
let typedTimer: ReturnType<typeof setTimeout> | undefined;
function typeAhead(char: string): void {
  typed.value += char.toLowerCase();
  clearTimeout(typedTimer);
  typedTimer = setTimeout(() => {
    typed.value = "";
  }, 500);
  const i = visibleOptions.value.findIndex((o) => labelOf(o).toLowerCase().startsWith(typed.value));
  if (i >= 0) moveFocus(i);
}

function onKeydown(event: KeyboardEvent): void {
  if (props.disabled) return;
  switch (event.key) {
    case "ArrowDown":
      event.preventDefault();
      if (!open.value) show();
      else moveFocus(focusIndex.value + 1);
      return;
    case "ArrowUp":
      event.preventDefault();
      if (!open.value) show();
      else moveFocus(focusIndex.value - 1);
      return;
    case "Home":
      if (!open.value) return;
      event.preventDefault();
      moveFocus(0);
      return;
    case "End":
      if (!open.value) return;
      event.preventDefault();
      moveFocus(visibleOptions.value.length - 1);
      return;
    case "Enter":
      event.preventDefault();
      if (!open.value) {
        show();
        return;
      }
      // With a filter box and nothing walked to, Enter takes the first
      // row the filter left standing.
      if (focusIndex.value < 0 && props.filter) moveFocus(0);
      if (visibleOptions.value[focusIndex.value]) choose(visibleOptions.value[focusIndex.value]);
      return;
    case " ":
      // The filter box owns the space bar while it has focus.
      if (props.filter && open.value) return;
      event.preventDefault();
      if (!open.value) show();
      else if (visibleOptions.value[focusIndex.value]) choose(visibleOptions.value[focusIndex.value]);
      return;
    case "Tab":
      close(false);
      return;
    default:
      if (!props.filter && open.value && event.key.length === 1 && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        typeAhead(event.key);
      }
  }
}

// Filtering changes the list under the roving focus, so the focus goes
// back to the top of what is left. The panel is also re-measured: a
// shorter list may now fit below the field.
watch(query, () => {
  focusIndex.value = -1;
  void nextTick(place);
});
</script>

<template>
  <div
    ref="root"
    class="ovl-field"
    :class="{ 'ovl-field-fluid': fluid, 'ovl-field-open': open, 'ovl-field-disabled': disabled }"
    role="combobox"
    :tabindex="disabled ? -1 : 0"
    :aria-expanded="open"
    :aria-controls="listId"
    aria-haspopup="listbox"
    :aria-disabled="disabled || undefined"
    :aria-activedescendant="open && focusIndex >= 0 ? optionId(focusIndex) : undefined"
    @click="toggleOpen"
    @keydown="onKeydown"
  >
    <span class="ovl-value" :class="{ 'ovl-value-placeholder': !hasValue }">
      <slot name="value" :value="modelValue" :placeholder="placeholder">{{
        hasValue ? displayLabel : placeholder
      }}</slot>
      <template v-if="!hasValue && !placeholder">&nbsp;</template>
    </span>

    <button
      v-if="showClear && hasValue && !disabled"
      type="button"
      class="ovl-clear"
      :aria-label="t('common.clear')"
      @click.stop="clear"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12" /></svg>
    </button>
    <span class="ovl-toggle" aria-hidden="true">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6" /></svg>
    </span>

    <Teleport to="body">
      <div v-if="open" ref="panel" class="ovl-panel" :style="panelStyle" @keydown="onKeydown">
        <div v-if="filter" class="ovl-header">
          <input
            ref="filterInput"
            v-model="query"
            type="text"
            class="ovl-filter"
            :placeholder="filterPlaceholder"
            autocomplete="off"
          />
        </div>
        <div class="ovl-list-container">
          <ul :id="listId" ref="listEl" class="ovl-list" role="listbox">
            <li
              v-for="(option, i) in visibleOptions"
              :id="optionId(i)"
              :key="i"
              class="ovl-option"
              :class="{
                'ovl-option-focus': i === focusIndex,
                'ovl-option-selected': valueOf(option) === modelValue,
              }"
              role="option"
              :aria-selected="valueOf(option) === modelValue"
              @click="choose(option)"
              @mousemove="focusIndex = i"
            >
              <slot name="option" :option="option" :index="i">{{ labelOf(option) }}</slot>
            </li>
            <li v-if="visibleOptions.length === 0" class="ovl-empty" role="option" aria-disabled="true">
              {{ t("common.noResults") }}
            </li>
          </ul>
        </div>
      </div>
    </Teleport>
  </div>
</template>
