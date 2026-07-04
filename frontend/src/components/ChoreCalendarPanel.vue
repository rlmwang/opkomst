<script setup lang="ts">
/**
 * One chore's roster calendar as a self-contained, full-width panel: a
 * heading (emoji + name) above a ``RosterCalendar`` (which owns the shared
 * ‹ month › grid). Each panel owns its month, so chores scroll
 * independently. Reads the current roster (``preview: false``) or the
 * post-"fold in" look-ahead (``preview: true``), picking its own chore out
 * of the month's response.
 */
import { computed, ref } from "vue";
import RosterCalendar from "./RosterCalendar.vue";
import { useRebalancePreviewCalendar, useRosterCalendar } from "@/composables/useChores";

const props = defineProps<{
  rosterId: string;
  choreId: string;
  choreName: string;
  emoji: string | null;
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
const days = computed(() => (query.data.value ?? []).find((c) => c.chore_id === props.choreId)?.days ?? []);
const hasChanges = computed(() => days.value.some((d) => d.changed));
</script>

<template>
  <section class="panel">
    <h3 class="panel-name">
      <span v-if="emoji" class="panel-emoji">{{ emoji }}</span>{{ choreName }}
    </h3>
    <p v-if="preview && noChangeLabel && !hasChanges" class="muted panel-note">{{ noChangeLabel }}</p>
    <RosterCalendar
      v-model:month="month"
      :days="days"
      :locale="locale"
      :open-label="openLabel"
      :anon-label="anonLabel"
      :prev-label="prevLabel"
      :next-label="nextLabel"
    />
  </section>
</template>

<style scoped>
.panel-name {
  margin: 0 0 0.5rem;
  font-size: 0.9375rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.panel-emoji {
  font-size: 1rem;
}
.panel-note {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
}
</style>
