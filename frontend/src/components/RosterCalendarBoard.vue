<script setup lang="ts">
/**
 * A month-navigable board of per-chore roster calendars: a ``‹ month ›``
 * navigator over one ``RosterCalendar`` per chore. Shared by the details
 * "Rooster" card (current roster) and the "fold in now" dialog (post-
 * rebalance look-ahead). ``month`` is a ``YYYY-MM`` string, v-model'd so the
 * parent owns which month is fetched.
 */
import Button from "primevue/button";
import { computed } from "vue";
import RosterCalendar from "./RosterCalendar.vue";
import type { ChoreCalendar } from "@/api/types";

const props = defineProps<{
  month: string;
  chores: ChoreCalendar[];
  locale: string;
  openLabel: string;
  anonLabel: string;
  prevLabel: string;
  nextLabel: string;
}>();
const emit = defineEmits<{ "update:month": [value: string] }>();

const year = computed(() => Number(props.month.split("-")[0]));
const monthIndex = computed(() => Number(props.month.split("-")[1]) - 1);
const monthLabel = computed(() =>
  new Intl.DateTimeFormat(props.locale, { month: "long", year: "numeric" }).format(new Date(year.value, monthIndex.value, 1)),
);

function shift(delta: number) {
  const d = new Date(year.value, monthIndex.value + delta, 1);
  emit("update:month", `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
}
</script>

<template>
  <div class="board">
    <div class="board-nav">
      <Button icon="pi pi-chevron-left" text rounded size="small" :aria-label="prevLabel" @click="shift(-1)" />
      <span class="board-month">{{ monthLabel }}</span>
      <Button icon="pi pi-chevron-right" text rounded size="small" :aria-label="nextLabel" @click="shift(1)" />
    </div>
    <div class="board-chores">
      <section v-for="c in chores" :key="c.chore_id" class="board-chore">
        <h3 class="board-chore-name">
          <span v-if="c.emoji" class="board-emoji">{{ c.emoji }}</span>{{ c.chore_name }}
        </h3>
        <RosterCalendar
          :year="year"
          :month="monthIndex"
          :days="c.days"
          :locale="locale"
          :open-label="openLabel"
          :anon-label="anonLabel"
        />
      </section>
    </div>
  </div>
</template>

<style scoped>
.board-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin: 0.25rem 0 1rem;
}
.board-month {
  font-weight: 600;
  min-width: 9rem;
  text-align: center;
  text-transform: capitalize;
}
.board-chores {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem 2rem;
}
.board-chore {
  min-width: 0;
}
.board-chore-name {
  margin: 0 0 0.5rem;
  font-size: 0.9375rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.board-emoji {
  font-size: 1rem;
}
</style>
