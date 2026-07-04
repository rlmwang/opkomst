<script setup lang="ts">
/**
 * Public personal-page calendar, built on the shared ``MonthGrid`` so it
 * matches the admin roster calendars exactly. Shows the volunteer's tasks
 * per day (chore names, comma-separated); confirmed days are solid,
 * tentative (expected) days dashed. Clicking a day that holds an actionable
 * shift opens a small popover with its action buttons.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import MonthGrid from "@/components/MonthGrid.vue";
import type { Locale } from "@/public_shared/strings";
import type { ShiftAction } from "./api";

export interface CalAction {
  key: ShiftAction;
  label: string;
  ghost?: boolean;
}
export interface CalEntry {
  id: string | null; // null = not actionable (expected/tentative)
  choreName: string;
  tentative: boolean;
  done?: boolean; // completed — shown ticked off, non-actionable
  missed?: boolean; // past, never done — shown struck through
  note?: string; // shown inline after the chore name in the popover
  actions?: CalAction[];
}

const props = defineProps<{
  month: string; // YYYY-MM
  entriesByDate: Record<string, CalEntry[]>;
  weekdays: readonly string[];
  prevLabel: string;
  nextLabel: string;
  locale: Locale;
  busy?: boolean;
}>();
const emit = defineEmits<{ "update:month": [value: string]; act: [id: string, key: ShiftAction] }>();

function dayClass(iso: string) {
  const es = props.entriesByDate[iso];
  return { occ: !!es?.length, tentative: !!es?.[0]?.tentative };
}
function actionable(iso: string): boolean {
  return (props.entriesByDate[iso] ?? []).some((e) => e.id && (e.actions?.length ?? 0) > 0);
}
// While a popover is open every other day is inert (no hover, no click): a
// click only dismisses the popover, which also avoids a double-toggle race.
function dayIsClickable(iso: string): boolean {
  return openIso.value === null && actionable(iso);
}

const openIso = ref<string | null>(null);
const openEntries = computed(() =>
  openIso.value ? (props.entriesByDate[openIso.value] ?? []).filter((e) => e.id && e.actions?.length) : [],
);
function onDayClick(iso: string) {
  openIso.value = openIso.value === iso ? null : iso;
}
function doAct(id: string, key: ShiftAction) {
  openIso.value = null;
  emit("act", id, key);
}

function close() {
  openIso.value = null;
}
watch(openIso, (v) => {
  if (v) setTimeout(() => document.addEventListener("click", close), 0);
  else document.removeEventListener("click", close);
});
onBeforeUnmount(() => document.removeEventListener("click", close));
</script>

<template>
  <MonthGrid
    :month="month"
    :locale="locale"
    :weekdays="weekdays"
    :prev-label="prevLabel"
    :next-label="nextLabel"
    :day-class="dayClass"
    :clickable="dayIsClickable"
    :active-iso="openIso"
    @update:month="(m: string) => emit('update:month', m)"
    @day-click="onDayClick"
  >
    <template #day="{ iso }">
      <ul v-if="entriesByDate[iso]" class="pcal-names">
        <li v-for="(e, j) in entriesByDate[iso]" :key="j" :class="{ done: e.done, missed: e.missed }">
          {{ e.choreName }}<span v-if="e.done" class="pcal-check" aria-hidden="true"> ✓</span>
        </li>
      </ul>
      <div v-if="openIso === iso" class="pcal-pop" @click.stop>
        <div v-for="(e, j) in openEntries" :key="j" class="pcal-pop-item">
          <div class="pcal-pop-title">
            {{ e.choreName }}<span v-if="e.note" class="pcal-pop-for"> · {{ e.note }}</span>
          </div>
          <div class="pcal-pop-actions">
            <button
              v-for="a in e.actions ?? []"
              :key="a.key"
              type="button"
              class="btn"
              :class="{ ghost: a.ghost }"
              :disabled="busy"
              @click="e.id && doAct(e.id, a.key)"
            >
              {{ a.label }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </MonthGrid>
</template>

<style scoped>
.pcal-names {
  list-style: none;
  margin: 0;
  padding: 0;
}
.pcal-names li {
  display: inline;
  font-size: 0.75rem;
  line-height: 1.3;
}
.pcal-names li:not(:last-child)::after {
  content: ", ";
  color: var(--brand-text-muted);
}
/* Finished shifts: done ticked off (green check), missed struck through. */
.pcal-names li.done {
  color: var(--brand-text-muted);
}
.pcal-names li.missed {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
.pcal-check {
  color: var(--brand-green);
}
.pcal-pop {
  pointer-events: auto;
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 12rem;
  max-width: 15rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  padding: 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  text-align: left;
}
.pcal-pop-title {
  font-weight: 600;
}
.pcal-pop-for {
  color: var(--brand-text-muted);
  font-weight: 400;
}
.pcal-pop-actions {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.5rem;
}
</style>
