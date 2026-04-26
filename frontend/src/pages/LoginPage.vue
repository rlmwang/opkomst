<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { useToast } from "primevue/usetoast";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const toast = useToast();

const email = ref("");
const password = ref("");
const submitting = ref(false);

async function submit() {
  submitting.value = true;
  try {
    await auth.login(email.value, password.value);
    const next = (route.query.next as string) || "/dashboard";
    void router.push(next);
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : "Inloggen mislukt";
    toast.add({ severity: "error", summary: msg, life: 3000 });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <div class="card stack">
      <h1>Inloggen</h1>
      <form class="stack" @submit.prevent="submit">
        <InputText v-model="email" type="email" placeholder="E-mailadres" required autocomplete="email" fluid />
        <Password v-model="password" placeholder="Wachtwoord" :feedback="false" toggle-mask required autocomplete="current-password" fluid />
        <Button type="submit" label="Inloggen" :loading="submitting" />
      </form>
      <p class="muted">
        Nog geen account?
        <router-link to="/register">Registreer hier</router-link>
        — een admin moet je nog goedkeuren voordat je evenementen kunt aanmaken.
      </p>
    </div>
  </div>
</template>
