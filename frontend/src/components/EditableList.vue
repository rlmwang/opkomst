<script setup lang="ts" generic="T">
import Button from "primevue/button";

defineProps<{
  /** The current items. */
  items: T[];
  /** How to render each item's label. */
  itemLabel: (item: T) => string;
  /** Stable per-item key for the v-for. */
  itemKey: (item: T) => string;
  /** Slot for a custom add control (typically an InputText with a + button). */
}>();

const emit = defineEmits<{
  remove: [item: T];
}>();

function ask(item: T) {
  emit("remove", item);
}
</script>

<template>
  <div class="editable-list">
    <div v-for="item in items" :key="itemKey(item)" class="row">
      <div class="row-label">
        <slot name="row" :item="item">
          <span>{{ itemLabel(item) }}</span>
        </slot>
      </div>
      <Button
        icon="pi pi-times"
        size="small"
        severity="secondary"
        text
        :aria-label="'Verwijder'"
        @click="ask(item)"
      />
    </div>
    <div class="add-row">
      <slot name="add" />
    </div>
  </div>
</template>

<style scoped>
.editable-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: space-between;
}
.row-label {
  flex: 1;
  min-width: 0;
}
.add-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}
.add-row :deep(.p-inputtext) {
  flex: 1;
}
</style>
