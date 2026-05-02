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
  /** Key of the row whose remove button is mid-flight (e.g. waiting
   * on a usage-fetch before opening a confirm dialog). The matching
   * trash button shows a spinner instead of the icon. */
  loadingKey?: string | null;
  /** Disable the trash button on every row (and surface it as a
   * non-interactive control). The list still renders the rows so
   * non-mutators can read the data. */
  readonly?: boolean;
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
    <div v-for="item in items" :key="itemKey(item)" class="list-row">
      <div class="list-row-label">
        <slot name="row" :item="item">
          <span>{{ itemLabel(item) }}</span>
        </slot>
      </div>
      <Button
        icon="pi pi-trash"
        size="small"
        severity="secondary"
        text
        :loading="loadingKey === itemKey(item)"
        :disabled="readonly"
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
.list-row-label {
  flex: 1;
  min-width: 0;
}
.add-row {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
/* Inputs grow to fill the row; buttons (and other auxiliary
 * controls) keep their natural size. The previous ``> * { flex: 1 }``
 * stretched the trailing plus-button to 50% of the row width. */
.add-row :deep(.p-autocomplete),
.add-row :deep(.p-inputtext) {
  flex: 1;
  min-width: 0;
  width: 100%;
}
</style>
