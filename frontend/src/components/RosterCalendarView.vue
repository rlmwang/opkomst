<script setup lang="ts">
/**
 * The one merged-roster month calendar, shared by the organiser details page
 * and the public "Bijspringen" overview. Presentational + dependency-free:
 * the caller supplies ``daysByIso`` (each chore's assignments folded per
 * date, emoji-tagged) and this renders them on the shared ``MonthGrid`` —
 * emoji + assignee per row, open in red, done ticked, missed struck through,
 * tentative days dashed, changed days ringed.
 *
 * Any assignment carrying an ``action`` makes its day tappable, opening a
 * popover. The default popover renders one button per action (the public
 * view's claim/cover); the ``popover`` slot lets a caller render its own
 * content instead (the organiser's hand-over pickers). While a popover is
 * open every other day is inert — a click only dismisses it.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import MonthGrid from "./MonthGrid.vue";

export interface RosterAction {
  shiftId: string;
  kind: string;
  label: string;
}
export interface RosterAssignment {
  emoji: string | null;
  name: string | null; // assignee pseudonym; null = open slot
  open: boolean;
  status: string; // scheduled | done | missed
  choreId?: string; // set by callers whose popover needs the chore (organiser hand-over)
  action?: RosterAction;
}
export interface RosterDay {
  assignments: RosterAssignment[];
  tentative: boolean;
  changed: boolean;
}

const props = defineProps<{
  month: string; // YYYY-MM
  daysByIso: Record<string, RosterDay>;
  weekdays: readonly string[];
  prevLabel: string;
  nextLabel: string;
  locale: string;
  openLabel: string;
  anonLabel: string;
  busy?: boolean;
}>();
const emit = defineEmits<{ "update:month": [value: string]; act: [shiftId: string, kind: string] }>();

function dayClass(iso: string) {
  const d = props.daysByIso[iso];
  return { occ: !!d?.assignments.length, tentative: !!d?.tentative, changed: !!d?.changed };
}
function actionable(iso: string): boolean {
  return (props.daysByIso[iso]?.assignments ?? []).some((a) => a.action);
}

const openIso = ref<string | null>(null);
// While a popover is open every other day is inert (no hover, no click): a
// click only dismisses the popover, which also avoids a double-toggle race
// between opening one day and closing another.
function dayIsClickable(iso: string): boolean {
  return openIso.value === null && actionable(iso);
}
const openActions = computed<RosterAction[]>(() =>
  openIso.value
    ? (props.daysByIso[openIso.value]?.assignments ?? []).flatMap((a) => (a.action ? [a.action] : []))
    : [],
);
function onDayClick(iso: string) {
  openIso.value = openIso.value === iso ? null : iso;
}
function doAct(a: RosterAction) {
  openIso.value = null;
  emit("act", a.shiftId, a.kind);
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
      <ul v-if="daysByIso[iso]?.assignments.length" class="rcv-list">
        <li
          v-for="(a, j) in daysByIso[iso].assignments"
          :key="j"
          class="rcv-item"
          :class="{ open: a.open, done: a.status === 'done', missed: a.status === 'missed' }"
        >
          <span v-if="a.emoji" class="rcv-emoji" aria-hidden="true">{{ a.emoji }}</span>
          <span class="rcv-name"
            >{{ a.open ? `(${openLabel})` : a.name || anonLabel
            }}<span v-if="a.status === 'done'" class="rcv-check" aria-hidden="true"> ✓</span></span
          >
        </li>
      </ul>
      <div v-if="openIso === iso" class="rcv-pop" @click.stop>
        <slot name="popover" :iso="iso" :assignments="daysByIso[iso]?.assignments ?? []" :close="close">
          <button v-for="(a, j) in openActions" :key="j" type="button" class="btn" :disabled="busy" @click="doAct(a)">
            {{ a.label }}
          </button>
        </slot>
      </div>
    </template>
  </MonthGrid>
</template>

<style scoped>
.rcv-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rcv-item {
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
  font-size: 0.75rem;
  line-height: 1.3;
}
.rcv-emoji {
  flex-shrink: 0;
}
.rcv-item.open .rcv-name {
  color: var(--brand-red);
}
.rcv-item.done .rcv-name {
  color: var(--brand-text-muted);
}
.rcv-item.missed .rcv-name {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
.rcv-check {
  color: var(--brand-green);
}
/* Claim/cover popover — matches the public ``.btn`` action buttons. */
.rcv-pop {
  pointer-events: auto;
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 11rem;
  max-width: 15rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  text-align: left;
}
/* The public mini-apps ship ``.btn`` from forms.css; the organiser (PrimeVue)
 * app does not, so provide the equivalent here for the read-only view (it has
 * no buttons anyway, but keep the popover self-sufficient). */
.rcv-pop .btn {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  cursor: pointer;
}
.rcv-pop .btn:hover:not(:disabled) {
  background: var(--brand-red-soft);
  border-color: var(--brand-red-soft-border);
}
</style>
