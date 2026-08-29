<script lang="ts">
/** What the field hands to ``@complete``: the text typed so far. */
export interface AutoCompleteCompleteEvent {
  originalEvent: Event;
  query: string;
}
/** What the field hands to ``@option-select``: the suggestion picked. */
export interface AutoCompleteOptionSelectEvent {
  originalEvent: Event;
  value: unknown;
}
</script>

<script setup lang="ts" generic="T">
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
import { computed, nextTick, ref, useId, watch } from "vue";
import { useI18n } from "@/i18n";

import { useOverlayPanel } from "@/composables/useOverlayPanel";
import "@/assets/overlay-list.css";

const props = withDefaults(
  defineProps<{
    modelValue?: unknown;
    suggestions?: readonly T[];
    optionLabel?: string;
    placeholder?: string;
    disabled?: boolean;
    /** Milliseconds of quiet typing before ``complete`` is emitted. */
    delay?: number;
    /** Shortest text worth asking about. */
    minLength?: number;
    fluid?: boolean;
  }>(),
  { delay: 300, minLength: 1 },
);

const emit = defineEmits<{
  "update:modelValue": [value: unknown];
  complete: [event: AutoCompleteCompleteEvent];
  "option-select": [event: AutoCompleteOptionSelectEvent];
  blur: [event: FocusEvent];
}>();

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
} = useOverlayPanel({
  onEscape: () => {
    typing.value = false;
    input.value?.focus();
  },
});

const input = ref<HTMLInputElement>();
const listEl = ref<HTMLElement>();
const focusIndex = ref(-1);
// True from the first keystroke until the field is left or a suggestion
// taken. A list that arrives after the user has stopped typing should
// not reopen the panel behind their back.
const typing = ref(false);

function labelOf(option: T): string {
  if (props.optionLabel && option !== null && typeof option === "object") {
    return String((option as Record<string, unknown>)[props.optionLabel] ?? "");
  }
  return String(option ?? "");
}

const items = computed(() => props.suggestions ?? []);

/** The model is a string while typing and an option once one is taken. */
const text = computed(() => {
  const v = props.modelValue;
  if (v === null || v === undefined) return "";
  return typeof v === "object" ? labelOf(v as T) : String(v);
});

let timer: ReturnType<typeof setTimeout> | undefined;

function onInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  emit("update:modelValue", value);
  clearTimeout(timer);
  if (value.length < props.minLength) {
    typing.value = false;
    hide();
    return;
  }
  typing.value = true;
  timer = setTimeout(() => {
    emit("complete", { originalEvent: event, query: value });
  }, props.delay);
}

// The caller answers ``complete`` by filling ``suggestions``. Showing
// the panel is this side's job, so the pickers stay declarative.
watch(items, (list) => {
  focusIndex.value = -1;
  if (!typing.value || list.length === 0) {
    hide();
    return;
  }
  if (open.value) void nextTick(place);
  else openPanel();
});

function choose(option: T, event: Event): void {
  emit("update:modelValue", option);
  emit("option-select", { originalEvent: event, value: option });
  typing.value = false;
  hide();
  input.value?.focus();
}

function scrollFocusedIntoView(): void {
  const row = listEl.value?.children[focusIndex.value] as HTMLElement | undefined;
  row?.scrollIntoView({ block: "nearest" });
}

function moveFocus(to: number): void {
  const n = items.value.length;
  if (n === 0) return;
  focusIndex.value = ((to % n) + n) % n;
  void nextTick(scrollFocusedIntoView);
}

function onKeydown(event: KeyboardEvent): void {
  switch (event.key) {
    case "ArrowDown":
      if (!open.value) return;
      event.preventDefault();
      moveFocus(focusIndex.value + 1);
      return;
    case "ArrowUp":
      if (!open.value) return;
      event.preventDefault();
      moveFocus(focusIndex.value - 1);
      return;
    case "Home":
      if (!open.value || focusIndex.value < 0) return;
      event.preventDefault();
      moveFocus(0);
      return;
    case "End":
      if (!open.value || focusIndex.value < 0) return;
      event.preventDefault();
      moveFocus(items.value.length - 1);
      return;
    case "Enter":
      if (!open.value) return;
      // Enter with nothing walked to leaves the text alone and closes
      // the list, so a caller that treats Enter as "make a new one"
      // still hears it.
      if (focusIndex.value >= 0 && items.value[focusIndex.value]) {
        event.preventDefault();
        choose(items.value[focusIndex.value], event);
      } else {
        typing.value = false;
        hide();
      }
      return;
    case "Tab":
      typing.value = false;
      hide();
  }
}

function onBlur(event: FocusEvent): void {
  typing.value = false;
  emit("blur", event);
}
</script>

<template>
  <div ref="root" class="ac" :class="{ 'ac-fluid': fluid }">
    <input
      ref="input"
      type="text"
      class="ac-input"
      :class="{ 'ac-input-fluid': fluid }"
      :value="text"
      :placeholder="placeholder"
      :disabled="disabled"
      role="combobox"
      :aria-expanded="open"
      :aria-controls="listId"
      aria-autocomplete="list"
      :aria-activedescendant="open && focusIndex >= 0 ? optionId(focusIndex) : undefined"
      autocomplete="off"
      @input="onInput"
      @keydown="onKeydown"
      @blur="onBlur"
    />

    <!-- ``mousedown.prevent`` keeps focus in the input while a
         suggestion is clicked, so the caller's ``blur`` handler does not
         run before the pick it was about to see. -->
    <Teleport to="body">
      <div
        v-if="open"
        ref="panel"
        class="ovl-panel"
        :style="panelStyle"
        @mousedown.prevent
      >
        <div class="ovl-list-container">
          <ul :id="listId" ref="listEl" class="ovl-list" role="listbox">
            <li
              v-for="(option, i) in items"
              :id="optionId(i)"
              :key="i"
              class="ovl-option"
              :class="{ 'ovl-option-focus': i === focusIndex }"
              role="option"
              :aria-selected="i === focusIndex"
              @click="choose(option, $event)"
              @mousemove="focusIndex = i"
            >
              <slot name="option" :option="option" :index="i">{{ labelOf(option) }}</slot>
            </li>
            <li v-if="items.length === 0" class="ovl-empty" role="option" aria-disabled="true">
              {{ t("common.noResults") }}
            </li>
          </ul>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
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
