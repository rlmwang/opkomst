<script setup lang="ts">
/**
 * The whole roster as one month calendar (all chores merged), built on the
 * shared ``MonthGrid``. Each occurrence renders as its chore's emoji followed
 * by the assignee — done ticked off (green), missed struck through, an open
 * slot in red. Reads the live roster (``preview: false``) or the post-"fold
 * in" look-ahead (``preview: true``, changed days ringed). Owns its month.
 */
import { computed, ref } from "vue";
import MonthGrid from "./MonthGrid.vue";
import { useRebalancePreviewCalendar, useRosterCalendar } from "@/composables/useChores";

const props = defineProps<{
  rosterId: string;
  preview?: boolean;
  enabled?: boolean;
  locale: string;
  openLabel: string;
  anonLabel: string;
  prevLabel: string;
  nextLabel: string;
  noChangeLabel?: string;
}>();

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const month = ref(currentMonth());
const rosterId = computed(() => props.rosterId);
const enabled = computed(() => props.enabled ?? true);
const query = props.preview
  ? useRebalancePreviewCalendar(rosterId, month, enabled)
  : useRosterCalendar(rosterId, month);

interface Assignment {
  emoji: string | null;
  name: string | null;
  open: boolean;
  status: string;
}
// Fold every chore's days into one per-date list of emoji-tagged assignments.
const byIso = computed(() => {
  const m = new Map<string, Assignment[]>();
  for (const chore of query.data.value ?? []) {
    for (const day of chore.days) {
      const list = m.get(day.on_date) ?? [];
      for (const a of day.assignees) list.push({ emoji: chore.emoji, name: a.name, open: a.open, status: a.status });
      m.set(day.on_date, list);
    }
  }
  return m;
});
const tentativeDays = computed(() => {
  const s = new Set<string>();
  for (const chore of query.data.value ?? []) for (const d of chore.days) if (d.tentative) s.add(d.on_date);
  return s;
});
const changedDays = computed(() => {
  const s = new Set<string>();
  for (const chore of query.data.value ?? []) for (const d of chore.days) if (d.changed) s.add(d.on_date);
  return s;
});
const hasChanges = computed(() => changedDays.value.size > 0);

const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
function dayClass(iso: string) {
  return { occ: byIso.value.has(iso), tentative: tentativeDays.value.has(iso), changed: changedDays.value.has(iso) };
}
</script>

<template>
  <div>
    <p v-if="preview && noChangeLabel && !hasChanges" class="muted rc-note">{{ noChangeLabel }}</p>
    <MonthGrid
      v-model:month="month"
      :locale="locale"
      :weekdays="weekdays"
      :prev-label="prevLabel"
      :next-label="nextLabel"
      :day-class="dayClass"
    >
      <template #day="{ iso }">
        <ul v-if="byIso.get(iso)?.length" class="rc-list">
          <li
            v-for="(a, j) in byIso.get(iso)"
            :key="j"
            class="rc-item"
            :class="{ open: a.open, done: a.status === 'done', missed: a.status === 'missed' }"
          >
            <span v-if="a.emoji" class="rc-emoji" aria-hidden="true">{{ a.emoji }}</span>
            <span class="rc-name">
              <span v-if="a.status === 'done'" class="rc-check" aria-hidden="true">✓ </span
              >{{ a.open ? openLabel : a.name || anonLabel }}
            </span>
          </li>
        </ul>
      </template>
    </MonthGrid>
  </div>
</template>

<style scoped>
.rc-note {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
}
.rc-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rc-item {
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
  font-size: 0.75rem;
  line-height: 1.3;
}
.rc-emoji {
  flex-shrink: 0;
}
.rc-item.open .rc-name {
  color: var(--brand-red);
}
.rc-item.done .rc-name {
  color: var(--brand-text-muted);
}
.rc-item.missed .rc-name {
  color: var(--brand-text-muted);
  text-decoration: line-through;
}
.rc-check {
  color: var(--brand-green);
}
</style>
