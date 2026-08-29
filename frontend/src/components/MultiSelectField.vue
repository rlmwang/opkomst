<script setup lang="ts" generic="T, V = unknown">
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
import { computed, nextTick, ref, useId, watch } from "vue";
import { useI18n } from "@/i18n";

import { useOverlayPanel } from "@/composables/useOverlayPanel";
import "@/assets/overlay-list.css";

const props = defineProps<{
  modelValue?: V[];
  options?: readonly T[];
  optionLabel?: string;
  optionValue?: string;
  placeholder?: string;
  disabled?: boolean;
  filter?: boolean;
  filterPlaceholder?: string;
  /** ``chip`` shows the chosen options as chips; anything else joins their labels with commas. */
  display?: "comma" | "chip";
  fluid?: boolean;
}>();

const emit = defineEmits<{ "update:modelValue": [value: V[]] }>();

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

const picked = computed(() => props.modelValue ?? []);
function isPicked(option: T): boolean {
  return picked.value.includes(valueOf(option));
}
/** The chosen options, in the order the caller's array holds them. */
const pickedOptions = computed(() =>
  picked.value
    .map((v) => allOptions.value.find((o) => valueOf(o) === v))
    .filter((o): o is T => o !== undefined),
);
const summary = computed(() => pickedOptions.value.map(labelOf).join(", "));

function show(): void {
  if (props.disabled || open.value) return;
  query.value = "";
  // Opening lands on the first row, so a single arrow press already has
  // somewhere to go.
  focusIndex.value = 0;
  openPanel();
  void nextTick(() => filterInput.value?.focus());
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

/** Choosing a row adds it; choosing it again takes it away. */
function toggleOption(option: T): void {
  const v = valueOf(option);
  const next = picked.value.includes(v)
    ? picked.value.filter((x) => x !== v)
    : [...picked.value, v];
  emit("update:modelValue", next);
}

function removeAt(index: number): void {
  const next = [...picked.value];
  next.splice(index, 1);
  emit("update:modelValue", next);
}

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
      if (focusIndex.value < 0 && props.filter) moveFocus(0);
      if (visibleOptions.value[focusIndex.value]) toggleOption(visibleOptions.value[focusIndex.value]);
      return;
    case " ":
      if (props.filter && open.value) return;
      event.preventDefault();
      if (!open.value) show();
      else if (visibleOptions.value[focusIndex.value]) toggleOption(visibleOptions.value[focusIndex.value]);
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

watch(query, () => {
  focusIndex.value = -1;
  void nextTick(place);
});
// Chips wrap, so the field grows as they are added and the panel has to
// follow it down the page.
watch(picked, () => void nextTick(place));
</script>

<template>
  <div
    ref="root"
    class="ovl-field ms-field"
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
    <span
      class="ovl-value"
      :class="{ 'ovl-value-placeholder': picked.length === 0, 'ms-value-chips': display === 'chip' }"
    >
      <template v-if="picked.length === 0">{{ placeholder }}&nbsp;</template>
      <template v-else-if="display === 'chip'">
        <span v-for="(option, i) in pickedOptions" :key="i" class="ms-chip">
          {{ labelOf(option) }}
          <button
            type="button"
            class="ms-chip-remove"
            :aria-label="t('common.remove')"
            @click.stop="removeAt(i)"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </span>
      </template>
      <template v-else>{{ summary }}</template>
    </span>

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
          <ul :id="listId" ref="listEl" class="ovl-list" role="listbox" aria-multiselectable="true">
            <li
              v-for="(option, i) in visibleOptions"
              :id="optionId(i)"
              :key="i"
              class="ovl-option"
              :class="{
                'ovl-option-focus': i === focusIndex,
                'ovl-option-selected': isPicked(option),
              }"
              role="option"
              :aria-selected="isPicked(option)"
              @click="toggleOption(option)"
              @mousemove="focusIndex = i"
            >
              <span class="ms-box" :class="{ 'ms-box-on': isPicked(option) }" aria-hidden="true">
                <svg v-if="isPicked(option)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
              </span>
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

<style scoped>
/* Chips wrap onto a second line rather than making the field scroll
 * sideways, which is what a chapter list with six picks needs. */
.ms-field {
  align-items: flex-start;
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
</style>

<style>
/* The checkbox in front of each row. The panel is teleported, so this
 * cannot be scoped. Aura's checkbox geometry: a 20px square with a 4px
 * radius that fills with the accent when it is on. */
.ovl-option .ms-box {
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
.ovl-option .ms-box-on {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
</style>
