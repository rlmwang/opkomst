<script setup lang="ts">
import ConfirmDialog from "primevue/confirmdialog";
import Toast from "primevue/toast";
import { onMounted } from "vue";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();

onMounted(() => {
  void auth.fetchMe();
});
</script>

<template>
  <Toast position="top-center" />
  <ConfirmDialog />
  <router-view />
  <LanguageSwitcher />
</template>
