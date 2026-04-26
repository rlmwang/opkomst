<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { useToast } from "primevue/usetoast";
import { ref } from "vue";
import { useRouter } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const toast = useToast();

const email = ref("");
const name = ref("");
const password = ref("");
const submitting = ref(false);

async function submit() {
  submitting.value = true;
  try {
    await auth.register(email.value, password.value, name.value);
    void router.push("/dashboard");
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : "Registratie mislukt";
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
      <h1>Registreren</h1>
      <p class="muted">
        Een account is alleen voor organisatoren. Na registratie moet een admin je goedkeuren voordat je evenementen kunt aanmaken.
      </p>
      <form class="stack" @submit.prevent="submit">
        <InputText v-model="name" placeholder="Naam" required fluid />
        <InputText v-model="email" type="email" placeholder="E-mailadres" required autocomplete="email" fluid />
        <Password v-model="password" placeholder="Wachtwoord (min. 8 tekens)" toggle-mask required autocomplete="new-password" fluid />
        <Button type="submit" label="Account aanmaken" :loading="submitting" />
      </form>
      <p class="muted">
        Al een account? <router-link to="/login">Inloggen</router-link>
      </p>
    </div>
  </div>
</template>
