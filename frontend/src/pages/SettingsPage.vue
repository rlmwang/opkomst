<script setup lang="ts">
/**
 * Organisation settings, third tab under Beheer.
 *
 * Today it holds one thing: how far the public chapter agenda
 * reaches in each direction. The window is a publishing decision
 * (how far ahead this organisation programmes), so it belongs
 * here rather than in a deploy variable.
 *
 * Admins write; organisers read. The form is a full replacement
 * of both numbers, saved on one button, because that is what the
 * endpoint takes.
 */
import Button from "primevue/button";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import NumberStepper from "@/components/NumberStepper.vue";
import { useSaveTenantSettings, useTenantSettings } from "@/composables/useTenantSettings";
import { can as permCan } from "@/lib/permissions";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();

// Same bounds the schema enforces, so the steppers can't offer a
// value the server would 422.
const MIN_DAYS = 1;
const MAX_DAYS = 365;

const settingsQuery = useTenantSettings();
const save = useSaveTenantSettings();

const canEdit = computed(() => permCan(auth.user, "update_settings"));
const loaded = computed(() => !settingsQuery.isPending.value);

// Local draft, seeded from the server and re-seeded whenever the
// query lands. Editing is local until Save, so a half-typed number
// never reaches the public page.
const futureDays = ref(31);
const pastDays = ref(60);
watch(
  settingsQuery.data,
  (s) => {
    if (!s) return;
    futureDays.value = s.agenda_future_days;
    pastDays.value = s.agenda_past_days;
  },
  { immediate: true },
);

const dirty = computed(() => {
  const s = settingsQuery.data.value;
  return (
    !!s && (s.agenda_future_days !== futureDays.value || s.agenda_past_days !== pastDays.value)
  );
});

async function submit() {
  try {
    await save.mutateAsync({
      agenda_future_days: futureDays.value,
      agenda_past_days: pastDays.value,
    });
    toasts.success(t("settings.saved"));
  } catch {
    toasts.error(t("settings.saveFailed"));
  }
}
</script>

<template>
  <AppHeader />
  <div class="container-wide stack">
    <h1>{{ t("settings.title") }}</h1>
    <p class="muted">{{ t("settings.intro") }}</p>

    <AppSkeleton v-if="!loaded" :rows="1" cards />

    <AppCard v-else tag="form" @submit.prevent="submit">
      <h2>{{ t("settings.agendaTitle") }}</h2>
      <p class="muted">{{ t("settings.agendaBody") }}</p>

      <!-- An organiser reads the same two numbers, as text. A
           stepper they cannot move would only invite the click. -->
      <div class="window-fields">
        <label class="window-field">
          <span>{{ t("settings.futureDays") }}</span>
          <NumberStepper
            v-if="canEdit"
            v-model="futureDays"
            :min="MIN_DAYS"
            :max="MAX_DAYS"
            :aria-label="t('settings.futureDays')"
          />
          <strong v-else>{{ t("settings.days", { n: futureDays }) }}</strong>
        </label>
        <label class="window-field">
          <span>{{ t("settings.pastDays") }}</span>
          <NumberStepper
            v-if="canEdit"
            v-model="pastDays"
            :min="MIN_DAYS"
            :max="MAX_DAYS"
            :aria-label="t('settings.pastDays')"
          />
          <strong v-else>{{ t("settings.days", { n: pastDays }) }}</strong>
        </label>
      </div>

      <div v-if="canEdit" class="save-row">
        <Button
          type="submit"
          :label="t('common.save')"
          :disabled="!dirty"
          :loading="save.isPending.value"
        />
      </div>
      <p v-else class="muted">{{ t("settings.readOnly") }}</p>
    </AppCard>
  </div>
</template>

<style scoped>
.window-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
}
.window-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.save-row {
  display: flex;
}
</style>
