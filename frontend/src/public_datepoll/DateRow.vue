<script setup lang="ts">
import type { Availability } from "./api";
import type { DatepollStrings } from "./i18n";

/** One candidate-date row: the date label, a yes/maybe/no segmented
 *  toggle, and an optional comment input. Two-way bound on ``state``
 *  and ``comment`` so it stays in sync with the calendar above (both
 *  views share the parent's answers map). */
defineProps<{
  label: string;
  state: Availability | null;
  comment: string;
  t: DatepollStrings;
}>();

const emit = defineEmits<{
  "update:state": [value: Availability];
  "update:comment": [value: string];
}>();

const OPTIONS: Availability[] = ["yes", "maybe", "no"];
</script>

<template>
  <div class="row">
    <div class="row-head">
      <span class="label">{{ label }}</span>
      <div class="seg" role="group">
        <button
          v-for="opt in OPTIONS"
          :key="opt"
          type="button"
          class="seg-btn"
          :class="[opt, { active: state === opt }]"
          @click="emit('update:state', opt)"
        >
          {{ t[opt] }}
        </button>
      </div>
    </div>
    <input
      class="comment"
      type="text"
      :value="comment"
      :placeholder="t.commentPlaceholder"
      maxlength="280"
      @input="emit('update:comment', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>

<style scoped>
.row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--brand-border);
}
.row:first-child { border-top: none; }
.row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.label { font-weight: 600; text-transform: capitalize; }
.seg { display: inline-flex; border: 1px solid var(--brand-border); border-radius: 8px; overflow: hidden; }
.seg-btn {
  border: none;
  background: var(--brand-surface);
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  cursor: pointer;
  color: var(--brand-text);
  border-left: 1px solid var(--brand-border);
}
.seg-btn:first-child { border-left: none; }
.seg-btn.active.yes { background: #1f7a3c; color: #fff; }
.seg-btn.active.maybe { background: #c98a00; color: #fff; }
.seg-btn.active.no { background: #6b6b6b; color: #fff; }
.comment {
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  font: inherit;
  background: var(--brand-surface);
}
</style>
