<script setup lang="ts">
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import { useToast } from "primevue/usetoast";
import { onMounted, ref } from "vue";
import { ApiError } from "@/api/client";
import { type EventOut, useEventsStore } from "@/stores/events";

const props = defineProps<{ slug: string }>();

const events = useEventsStore();
const toast = useToast();

const event = ref<EventOut | null>(null);
const error = ref<string | null>(null);

const displayName = ref("");
const partySize = ref(1);
const sourceChoice = ref<string | null>(null);
const email = ref("");
const submitting = ref(false);
const submitted = ref(false);

onMounted(async () => {
  try {
    event.value = await events.getBySlug(props.slug);
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 404 ? "Evenement niet gevonden" : "Kon evenement niet laden";
  }
});

async function submit() {
  if (!event.value || !sourceChoice.value) return;
  submitting.value = true;
  try {
    await events.signUp(props.slug, {
      display_name: displayName.value,
      party_size: partySize.value,
      source_choice: sourceChoice.value,
      email: email.value.trim() ? email.value.trim() : null,
    });
    submitted.value = true;
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : "Aanmelden mislukt";
    toast.add({ severity: "error", summary: msg, life: 3000 });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="container stack">
    <header class="public-header">
      <span class="brand">opkomst</span>
    </header>

    <div v-if="error" class="card">
      <p>{{ error }}</p>
    </div>

    <template v-else-if="event">
      <div class="card stack">
        <h1>{{ event.name }}</h1>
        <p v-if="event.topic" class="muted">{{ event.topic }}</p>
        <p>
          <strong>{{ event.location }}</strong><br />
          {{ new Date(event.starts_at).toLocaleString("nl-NL") }}
        </p>
      </div>

      <div v-if="submitted" class="card stack">
        <h2>Bedankt — je aanmelding is binnen.</h2>
        <p class="muted">
          Tot dan! Als je een e-mailadres hebt achtergelaten ontvang je de dag na het evenement één korte feedbackvraag. Daarna verwijderen we je adres.
        </p>
      </div>

      <form v-else class="card stack" @submit.prevent="submit">
        <h2>Aanmelden</h2>
        <p class="privacy-notice">
          We vragen alleen wat we nodig hebben. Je naam mag een schuilnaam zijn —
          die helpt ons alleen bij de hoofdtelling. Je e-mailadres is optioneel,
          wordt versleuteld bewaard en éénmalig gebruikt voor een feedbackmail
          na afloop. Daarna wissen we het permanent. De volledige broncode van
          deze app staat
          <a href="https://github.com/" target="_blank" rel="noopener">openbaar online</a>.
        </p>
        <InputText v-model="displayName" placeholder="Naam (mag een schuilnaam zijn)" required fluid />
        <InputNumber v-model="partySize" :min="1" :max="50" placeholder="Aantal personen (incl. jezelf)" show-buttons fluid />
        <Select
          v-model="sourceChoice"
          :options="event.source_options"
          placeholder="Hoe heb je ons gevonden?"
          required
          fluid
        />
        <InputText v-model="email" type="email" placeholder="E-mailadres (optioneel, voor één feedbackmail)" autocomplete="email" fluid />
        <Button type="submit" label="Aanmelden" :loading="submitting" />
      </form>
    </template>
  </div>
</template>

<style scoped>
.public-header {
  padding: 1rem 0;
}
.brand {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--brand-red);
  letter-spacing: 0.5px;
}
</style>
