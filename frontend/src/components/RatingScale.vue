<script setup lang="ts">
defineProps<{
  modelValue: number | null;
  labelLow: string;
  labelHigh: string;
}>();

defineEmits<{
  "update:modelValue": [value: number];
}>();

const VALUES = [1, 2, 3, 4, 5];
</script>

<template>
  <div class="rating">
    <div class="row">
      <button
        v-for="v in VALUES"
        :key="v"
        type="button"
        class="dot"
        :class="{ active: modelValue === v }"
        :aria-label="String(v)"
        @click="$emit('update:modelValue', v)"
      >
        {{ v }}
      </button>
    </div>
    <div class="legend">
      <span>{{ labelLow }}</span>
      <span>{{ labelHigh }}</span>
    </div>
  </div>
</template>

<style scoped>
.rating {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.row {
  display: flex;
  gap: 0.5rem;
}
.dot {
  flex: 1;
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
  font-size: 1rem;
  font-weight: 600;
  padding: 0.625rem 0;
  border-radius: 8px;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.dot:hover {
  border-color: var(--brand-red);
}
.dot.active {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #fff;
}
.legend {
  display: flex;
  justify-content: space-between;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}
</style>
