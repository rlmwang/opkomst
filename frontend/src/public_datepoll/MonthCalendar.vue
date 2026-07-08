<script setup lang="ts">
/**
 * One month of a datepoll's candidate days for public voting, built on the
 * shared ``MonthGrid`` (so it matches every other calendar). Each candidate
 * day shows one tri-state pill per slot (whole-day → a single pill; timed →
 * a pill per time range). Tapping a pill cycles its state; the parent owns
 * the cycle. Rendered one grid per month (no navigator — months stack).
 */
import { computed } from "vue";
import MonthGrid from "@/components/MonthGrid.vue";
import type { Availability } from "./api";
import type { Locale } from "@/public_shared/strings";

interface SlotCell {
  id: string;
  label: string | null; // null = whole-day
}

const props = defineProps<{
  year: number;
  month: number; // 0-based
  slotsByIso: Record<string, SlotCell[]>;
  answers: Record<string, Availability | null>;
  locale: Locale;
  // Shared column template (see PublicDatepoll): one fixed grid so every
  // stacked month lines up with the next and with the weekday header.
  columns: string;
}>();
const emit = defineEmits<{ toggle: [slotId: string] }>();

const GLYPH: Record<Availability, string> = { yes: "✓", maybe: "~", no: "✕" };
const monthStr = computed(() => `${props.year}-${String(props.month + 1).padStart(2, "0")}`);
const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
function dayClass(iso: string) {
  return { occ: !!props.slotsByIso[iso]?.length };
}
</script>

<template>
  <MonthGrid :month="monthStr" :locale="locale" :weekdays="weekdays" :nav="false" :day-class="dayClass" :columns="columns">
    <template #day="{ iso }">
      <div v-if="slotsByIso[iso]?.length" class="votes">
        <button
          v-for="s in slotsByIso[iso]"
          :key="s.id"
          type="button"
          class="vote"
          :class="answers[s.id] ?? 'unset'"
          @click.stop="emit('toggle', s.id)"
        >
          <span v-if="s.label" class="vote-time">{{ s.label }}</span>
          <span class="vote-glyph">{{ answers[s.id] ? GLYPH[answers[s.id] as Availability] : s.label ? "" : "·" }}</span>
        </button>
      </div>
    </template>
  </MonthGrid>
</template>

<style scoped>
.votes {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  pointer-events: auto;
}
.vote {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.1875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-bg);
  color: var(--brand-text);
  cursor: pointer;
  padding: 0.25rem 0.125rem;
  font-size: 0.6875rem;
  line-height: 1.1;
}
.vote.unset {
  border-style: dashed;
}
.vote-time {
  white-space: nowrap;
}
.vote.yes {
  background: var(--brand-green);
  color: #fff;
  border-color: var(--brand-green);
}
.vote.maybe {
  background: var(--brand-amber);
  color: #fff;
  border-color: var(--brand-amber);
}
.vote.no {
  background: #6b6b6b;
  color: #fff;
  border-color: #6b6b6b;
}
</style>
