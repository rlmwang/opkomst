<script setup lang="ts">
import Dialog from "primevue/dialog";

defineProps<{
  visible: boolean;
  header: string;
  width?: string;
}>();

defineEmits<{ "update:visible": [value: boolean] }>();
</script>

<template>
  <Dialog
    :visible="visible"
    :header="header"
    modal
    :style="{ width: width ?? '420px' }"
    @update:visible="(v: boolean) => $emit('update:visible', v)"
  >
    <div class="app-dialog-body">
      <slot />
    </div>
    <template #footer>
      <div class="app-dialog-footer">
        <slot name="footer" />
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.app-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.app-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
