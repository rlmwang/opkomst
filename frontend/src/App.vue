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
  <!-- Match AppDialog's default width so confirmation dialogs and
       form dialogs sit at exactly the same size, regardless of how
       long the message text happens to be. -->
  <ConfirmDialog :style="{ width: '420px' }" />

  <router-view />
  <LanguageSwitcher />
</template>
