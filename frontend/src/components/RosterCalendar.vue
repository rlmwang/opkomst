<script setup lang="ts">
/**
 * The organiser's roster calendar: fetches the whole roster for a month
 * (live, or the post-"fold in" look-ahead) and feeds the shared, read-only
 * ``RosterCalendarView``. Owns its month so chores/panels scroll on their
 * own. Assignments carry no action here — the organiser view is read-only.
 */
import { computed, ref } from "vue";
import RosterCalendarView, { type RosterDay } from "./RosterCalendarView.vue";
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

// Fold every chore's days into one per-date bucket of emoji-tagged assignments.
const daysByIso = computed<Record<string, RosterDay>>(() => {
  const map: Record<string, RosterDay> = {};
  for (const chore of query.data.value ?? []) {
    for (const day of chore.days) {
      const d = (map[day.on_date] ??= { assignments: [], tentative: false, changed: false });
      if (day.tentative) d.tentative = true;
      if (day.changed) d.changed = true;
      for (const a of day.assignees) {
        d.assignments.push({ emoji: chore.emoji, name: a.name, open: a.open, status: a.status });
      }
    }
  }
  return map;
});
const hasChanges = computed(() => Object.values(daysByIso.value).some((d) => d.changed));

const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
</script>

<template>
  <div>
    <p v-if="preview && noChangeLabel && !hasChanges" class="muted rc-note">{{ noChangeLabel }}</p>
    <RosterCalendarView
      v-model:month="month"
      :days-by-iso="daysByIso"
      :weekdays="weekdays"
      :prev-label="prevLabel"
      :next-label="nextLabel"
      :locale="locale"
      :open-label="openLabel"
      :anon-label="anonLabel"
    />
  </div>
</template>

<style scoped>
.rc-note {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
}
</style>
