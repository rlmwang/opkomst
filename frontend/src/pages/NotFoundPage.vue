<script setup lang="ts">
import AppHeader from "@/components/AppHeader.vue";
</script>

<template>
  <AppHeader />
  <div class="container">
    <div class="card">
      <h1>404</h1>
      <p>Deze pagina bestaat niet.</p>
      <router-link to="/">Terug naar het begin</router-link>
    </div>
  </div>
</template>
