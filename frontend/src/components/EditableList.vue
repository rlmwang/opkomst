<script setup lang="ts" generic="T">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";

defineProps<{
  /** The current items. */
  items: T[];
  /** How to render each item's label. */
  itemLabel: (item: T) => string;
  /** Stable per-item key for the v-for. */
  itemKey: (item: T) => string;
}>();

const emit = defineEmits<{
  remove: [item: T];
}>();

const { t } = useI18n();

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
        :aria-label="t('common.remove')"
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
  padding: 0.375rem 0.5rem;
  border-radius: 6px;
  transition: background 120ms ease;
}
.row:hover {
  background: var(--brand-bg);
}
.row-label {
  flex: 1;
  min-width: 0;
}
.add-row {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0 0.5rem;
}
.add-row > * {
  flex: 1;
  min-width: 0;
}
.add-row :deep(.p-autocomplete),
.add-row :deep(.p-inputtext) {
  width: 100%;
}
</style>
