<script setup lang="ts">
import AppInput from "@/components/AppInput.vue";
import { useI18n } from "@/i18n";

/**
 * The one field a create form grows when it is opened by somebody with
 * no account: their address.
 *
 * It sits above the rest of the form. The address is the account here:
 * it owns what gets made, and it is where the sign-in link goes. One
 * component so all four create pages ask for it the same way.
 */

const model = defineModel<string>({ required: true });
const { t } = useI18n();
</script>

<template>
  <AppInput
    v-model="model"
    type="email"
    name="email"
    :placeholder="t('start.emailPlaceholder')"
    autocomplete="email"
    fluid
  />
</template>
