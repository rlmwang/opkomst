<script setup lang="ts">
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import { useToast } from "primevue/usetoast";
import { ref } from "vue";
import { useRouter } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import LocationPicker from "@/components/LocationPicker.vue";
import { ApiError } from "@/api/client";
import { useEventsStore } from "@/stores/events";

const router = useRouter();
const events = useEventsStore();
const toast = useToast();

const name = ref("");
const topic = ref("");
const location = ref("");
const latitude = ref<number | null>(null);
const longitude = ref<number | null>(null);
const startsAt = ref<Date | null>(null);
const endsAt = ref<Date | null>(null);
const sources = ref<string[]>(["Flyer", "Mond-tot-mond", "Social media"]);
const newSource = ref("");
const submitting = ref(false);

function addSource() {
  const v = newSource.value.trim();
  if (!v || sources.value.includes(v)) return;
  sources.value.push(v);
  newSource.value = "";
}

function removeSource(i: number) {
  sources.value.splice(i, 1);
}

async function submit() {
  if (!startsAt.value || !endsAt.value) {
    toast.add({ severity: "warn", summary: "Vul start- en eindtijd in", life: 3000 });
    return;
  }
  submitting.value = true;
  try {
    const created = await events.create({
      name: name.value,
      topic: topic.value || null,
      location: location.value,
      latitude: latitude.value,
      longitude: longitude.value,
      starts_at: startsAt.value.toISOString(),
      ends_at: endsAt.value.toISOString(),
      source_options: sources.value,
    });
    void router.push(`/events/${created.id}/stats`);
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : "Aanmaken mislukt";
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
      <h1>Nieuw evenement</h1>
      <form class="stack" @submit.prevent="submit">
        <InputText v-model="name" placeholder="Naam van het evenement" required fluid />
        <InputText v-model="topic" placeholder="Onderwerp (optioneel)" fluid />
        <LocationPicker
          v-model="location"
          :latitude="latitude"
          :longitude="longitude"
          @update:coords="(c) => { latitude = c.latitude; longitude = c.longitude; }"
        />
        <DatePicker v-model="startsAt" show-time hour-format="24" placeholder="Starttijd" fluid />
        <DatePicker v-model="endsAt" show-time hour-format="24" placeholder="Eindtijd" fluid />

        <div class="stack">
          <label class="muted">Hoe heb je ons gevonden? — opties voor de aanmeldformulier:</label>
          <div v-for="(src, i) in sources" :key="i" class="source-row">
            <span>{{ src }}</span>
            <Button icon="pi pi-times" size="small" severity="secondary" text @click="removeSource(i)" />
          </div>
          <div class="source-row">
            <InputText v-model="newSource" placeholder="Nieuwe optie toevoegen" fluid @keydown.enter.prevent="addSource" />
            <Button icon="pi pi-plus" size="small" severity="secondary" @click="addSource" />
          </div>
        </div>

        <Button type="submit" label="Evenement aanmaken" :loading="submitting" />
      </form>
    </div>
  </div>
</template>

<style scoped>
.source-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: space-between;
}
</style>
