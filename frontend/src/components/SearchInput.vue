<script setup lang="ts">
/** A search field with the magnifier sitting inside it. The icon and
 *  its clearance were PrimeVue's ``IconField`` / ``InputIcon``, which
 *  is a wrapper, an absolutely-positioned icon, and padding on the
 *  input. That is cheaper written here than imported. */
import AppInput from "@/components/AppInput.vue";

defineProps<{
  modelValue: string;
  placeholder: string;
}>();

defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <div class="icon-field">
    <i class="pi pi-search field-icon" aria-hidden="true"></i>
    <AppInput
      :model-value="modelValue"
      :placeholder="placeholder"
      fluid
      @update:model-value="(v: string | null | undefined) => $emit('update:modelValue', v ?? '')"
    />
  </div>
</template>

<style scoped>
.icon-field {
  position: relative;
  display: block;
}
.field-icon {
  position: absolute;
  top: 50%;
  inset-inline-start: 0.75rem;
  margin-top: -0.5rem;
  color: var(--brand-surface-400);
  line-height: 1;
  z-index: 1;
}
/* Twice the field's own inline padding, plus the icon, so the text
 * starts clear of it. */
.icon-field :deep(.app-input) {
  padding-inline-start: 2.5rem;
}
</style>
