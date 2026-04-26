<script setup lang="ts">
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import InputText from "primevue/inputtext";
import { useToast } from "primevue/usetoast";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import LocationPicker from "@/components/LocationPicker.vue";
import { ApiError } from "@/api/client";
import { useEventsStore } from "@/stores/events";

const props = defineProps<{ eventId?: string }>();

const { t } = useI18n();
const router = useRouter();
const events = useEventsStore();
const toast = useToast();

const isEdit = computed(() => Boolean(props.eventId));

const name = ref("");
const topic = ref("");
const location = ref("");
const latitude = ref<number | null>(null);
const longitude = ref<number | null>(null);
const eventDate = ref<Date | null>(null);
const startTime = ref<Date | null>(null);
const endTime = ref<Date | null>(null);
const sources = ref<string[]>(["Flyer", "Mond-tot-mond", "Social media"]);
const newSource = ref("");
const submitting = ref(false);

function combine(date: Date, time: Date): Date {
  const d = new Date(date);
  d.setHours(time.getHours(), time.getMinutes(), 0, 0);
  return d;
}

function addSource() {
  const v = newSource.value.trim();
  if (!v || sources.value.includes(v)) return;
  sources.value.push(v);
  newSource.value = "";
}

function removeSource(i: number) {
  sources.value.splice(i, 1);
}

onMounted(async () => {
  if (!isEdit.value) return;
  if (events.all.length === 0) await events.fetchAll();
  const existing = events.all.find((e) => e.id === props.eventId);
  if (!existing) {
    toast.add({ severity: "error", summary: t("event.notFound"), life: 3000 });
    return;
  }
  name.value = existing.name;
  topic.value = existing.topic ?? "";
  location.value = existing.location;
  latitude.value = existing.latitude;
  longitude.value = existing.longitude;
  const start = new Date(existing.starts_at);
  const end = new Date(existing.ends_at);
  eventDate.value = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  startTime.value = new Date(start);
  endTime.value = new Date(end);
  sources.value = [...existing.source_options];
});

async function submit() {
  if (!eventDate.value || !startTime.value || !endTime.value) {
    toast.add({ severity: "warn", summary: t("event.fillTimes"), life: 3000 });
    return;
  }
  const startsAt = combine(eventDate.value, startTime.value);
  const endsAt = combine(eventDate.value, endTime.value);
  if (endsAt <= startsAt) {
    toast.add({ severity: "warn", summary: t("event.endAfterStart"), life: 3000 });
    return;
  }
  submitting.value = true;
  try {
    const payload = {
      name: name.value,
      topic: topic.value || null,
      location: location.value,
      latitude: latitude.value,
      longitude: longitude.value,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      source_options: sources.value,
    };
    const result =
      isEdit.value && props.eventId
        ? await events.update(props.eventId, payload)
        : await events.create(payload);
    void router.push(`/events/${result.id}/details`);
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : t("event.saveFailed");
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
      <h1>{{ isEdit ? t("event.editTitle") : t("event.newTitle") }}</h1>
      <form class="stack" @submit.prevent="submit">
        <InputText v-model="name" :placeholder="t('event.name')" required fluid />
        <InputText v-model="topic" :placeholder="t('event.topic')" fluid />
        <LocationPicker
          v-model="location"
          :latitude="latitude"
          :longitude="longitude"
          @update:coords="(c) => { latitude = c.latitude; longitude = c.longitude; }"
        />
        <DatePicker v-model="eventDate" date-format="dd-mm-yy" :placeholder="t('event.date')" fluid />
        <div class="time-row">
          <DatePicker
            v-model="startTime"
            time-only
            hour-format="24"
            :step-minute="15"
            :placeholder="t('event.startTime')"
            fluid
          />
          <DatePicker
            v-model="endTime"
            time-only
            hour-format="24"
            :step-minute="15"
            :placeholder="t('event.endTime')"
            fluid
          />
        </div>

        <div class="stack">
          <label class="muted">{{ t("event.sourcesLabel") }}</label>
          <div v-for="(src, i) in sources" :key="i" class="source-row">
            <span>{{ src }}</span>
            <Button icon="pi pi-times" size="small" severity="secondary" text @click="removeSource(i)" />
          </div>
          <div class="source-row">
            <InputText v-model="newSource" :placeholder="t('event.newSource')" fluid @keydown.enter.prevent="addSource" />
            <Button icon="pi pi-plus" size="small" severity="secondary" @click="addSource" />
          </div>
        </div>

        <Button type="submit" :label="isEdit ? t('event.save') : t('event.create')" :loading="submitting" />
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
.time-row {
  display: flex;
  gap: 0.5rem;
}
.time-row > * {
  flex: 1;
}
</style>
