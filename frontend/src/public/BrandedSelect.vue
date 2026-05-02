<script setup lang="ts">
/**
 * Brand-styled single-select dropdown for the public mini-app.
 *
 * Native ``<select>`` works for input, but its open panel is
 * rendered by the OS — Chrome/Firefox/Safari all show their own
 * non-themable list, which made the public form look stylistically
 * adrift from the rest of the cream/red brand. PrimeVue's Select
 * (which the previous page used) drew a fully-themed panel.
 *
 * This is a minimal accessible re-implementation: button trigger
 * + floating listbox + arrow / enter / escape key handling +
 * click-outside-to-close. ~80 LOC, no extra deps.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  modelValue: string | null;
  options: readonly string[];
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string | null];
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const listEl = ref<HTMLElement | null>(null);
// "Active descendant" — keyboard-highlighted option, separate from
// the committed value. Reset to current selection when opened.
const activeIndex = ref(-1);

// ``items`` includes the placeholder as the first row so visitors
// can re-pick it to clear — same affordance as a re-clickable
// disabled option in a native select.
interface Item {
  value: string | null;
  label: string;
}
const items = computed<Item[]>(() => [
  { value: null, label: props.placeholder ?? "" },
  ...props.options.map((o) => ({ value: o, label: o })),
]);

const selectedLabel = computed(() => {
  const item = items.value.find((i) => i.value === props.modelValue);
  return item ? item.label : (props.placeholder ?? "");
});
const isPlaceholder = computed(() => props.modelValue === null);

function toggle() {
  if (props.disabled) return;
  open.value = !open.value;
  if (open.value) {
    activeIndex.value = items.value.findIndex((i) => i.value === props.modelValue);
    if (activeIndex.value < 0) activeIndex.value = 0;
    void nextTick(scrollActiveIntoView);
  }
}
function close() { open.value = false; }
function pick(item: Item) {
  emit("update:modelValue", item.value);
  open.value = false;
}
function onKeydown(ev: KeyboardEvent) {
  if (props.disabled) return;
  if (!open.value) {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(ev.key)) {
      ev.preventDefault();
      toggle();
    }
    return;
  }
  if (ev.key === "Escape") { ev.preventDefault(); close(); return; }
  if (ev.key === "Enter" || ev.key === " ") {
    ev.preventDefault();
    if (activeIndex.value >= 0) pick(items.value[activeIndex.value]);
    return;
  }
  if (ev.key === "ArrowDown") {
    ev.preventDefault();
    activeIndex.value = Math.min(items.value.length - 1, activeIndex.value + 1);
    void nextTick(scrollActiveIntoView);
  }
  if (ev.key === "ArrowUp") {
    ev.preventDefault();
    activeIndex.value = Math.max(0, activeIndex.value - 1);
    void nextTick(scrollActiveIntoView);
  }
  if (ev.key === "Home") { ev.preventDefault(); activeIndex.value = 0; void nextTick(scrollActiveIntoView); }
  if (ev.key === "End") { ev.preventDefault(); activeIndex.value = items.value.length - 1; void nextTick(scrollActiveIntoView); }
}
function scrollActiveIntoView() {
  const el = listEl.value?.children[activeIndex.value] as HTMLElement | undefined;
  el?.scrollIntoView({ block: "nearest" });
}

// Click-outside dismiss.
function onDocClick(ev: MouseEvent) {
  if (!open.value) return;
  const node = ev.target as Node | null;
  if (root.value && node && !root.value.contains(node)) close();
}
onMounted(() => document.addEventListener("click", onDocClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));

// If the visitor disables the field while it's open (event data
// resets, etc.), close the panel.
watch(() => props.disabled, (v) => { if (v) close(); });

const triggerId = `branded-select-${Math.random().toString(36).slice(2, 9)}`;
</script>

<template>
  <div ref="root" class="branded-select" :class="{ open, disabled }">
    <button
      :id="triggerId"
      type="button"
      class="trigger input"
      :disabled="disabled"
      :aria-haspopup="'listbox'"
      :aria-expanded="open"
      :aria-label="ariaLabel"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="trigger-label" :class="{ placeholder: isPlaceholder }">
        {{ selectedLabel }}
      </span>
      <span class="chevron" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </span>
    </button>
    <ul
      v-if="open"
      ref="listEl"
      class="listbox"
      role="listbox"
      :aria-labelledby="triggerId"
      tabindex="-1"
    >
      <li
        v-for="(item, i) in items"
        :key="i"
        :class="['option', {
          active: i === activeIndex,
          selected: item.value === modelValue,
          'is-placeholder': item.value === null,
        }]"
        role="option"
        :aria-selected="item.value === modelValue"
        @mousedown.prevent="pick(item)"
        @mouseenter="activeIndex = i"
      >
        <span class="option-label">{{ item.label }}</span>
        <svg
          v-if="item.value === modelValue && item.value !== null"
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
      </li>
    </ul>
  </div>
</template>

<style scoped>
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
