<script setup lang="ts">
/**
 * One chore's roster calendar as a self-contained, full-width panel: a
 * heading (emoji + name) with its own ``‹ month ›`` navigator, and the
 * month grid below. Each panel owns its month, so chores scroll
 * independently. Reads the current roster (``preview: false``) or the
 * post-"fold in" look-ahead (``preview: true``), picking its own chore out
 * of the month's response.
 */
import Button from "primevue/button";
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
const year = computed(() => Number(month.value.split("-")[0]));
const monthIdx = computed(() => Number(month.value.split("-")[1]) - 1);
const monthLabel = computed(() =>
  new Intl.DateTimeFormat(props.locale, { month: "long", year: "numeric" }).format(new Date(year.value, monthIdx.value, 1)),
);
function shift(delta: number) {
  const d = new Date(year.value, monthIdx.value + delta, 1);
  month.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

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
    <div class="panel-head">
      <h3 class="panel-name">
        <span v-if="emoji" class="panel-emoji">{{ emoji }}</span>{{ choreName }}
      </h3>
      <div class="panel-nav">
        <Button icon="pi pi-chevron-left" text rounded size="small" :aria-label="prevLabel" @click="shift(-1)" />
        <span class="panel-month">{{ monthLabel }}</span>
        <Button icon="pi pi-chevron-right" text rounded size="small" :aria-label="nextLabel" @click="shift(1)" />
      </div>
    </div>
    <p v-if="preview && noChangeLabel && !hasChanges" class="muted panel-note">{{ noChangeLabel }}</p>
    <RosterCalendar
      :year="year"
      :month="monthIdx"
      :days="days"
      :locale="locale"
      :open-label="openLabel"
      :anon-label="anonLabel"
    />
  </section>
</template>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.panel-name {
  margin: 0;
  font-size: 0.9375rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.panel-emoji {
  font-size: 1rem;
}
.panel-nav {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.panel-month {
  font-weight: 600;
  min-width: 8.5rem;
  text-align: center;
  text-transform: capitalize;
}
.panel-note {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
}
</style>
