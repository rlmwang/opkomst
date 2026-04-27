<script setup lang="ts">
import IconField from "primevue/iconfield";
import InputIcon from "primevue/inputicon";
import InputText from "primevue/inputtext";

defineProps<{
  modelValue: string;
  placeholder: string;
}>();

defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <IconField>
    <InputIcon class="pi pi-search" />
    <InputText
      :model-value="modelValue"
      :placeholder="placeholder"
      fluid
      @update:model-value="(v: string | undefined) => $emit('update:modelValue', v ?? '')"
    />
  </IconField>
</template>
