<script lang="ts">
/**
 * Organisation settings, the third tab under Beheer.
 *
 * Today it holds one thing: how far the public chapter agenda reaches
 * in each direction. That is a publishing decision, how far ahead this
 * organisation programmes, so it belongs here and not in a deploy
 * variable.
 *
 * Admins write, organisers read. The form replaces both numbers on one
 * button, because that is what the endpoint takes.
 */
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppSkeleton from "@/components/AppSkeleton.svelte";
import NumberStepper from "@/components/NumberStepper.svelte";
import {
  saveTenantSettings,
  tenantSettingsQuery,
} from "@/composables/useTenantSettings.svelte";
import { t } from "@/i18n.svelte";
import { can } from "@/lib/permissions";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";

const toasts = useToasts();

/** The bounds the schema enforces, so a stepper cannot offer a value
 *  the server would refuse. */
const MIN_DAYS = 1;
const MAX_DAYS = 365;

const query = tenantSettingsQuery();
const save = saveTenantSettings();

const canEdit = $derived(can(auth.user, "update_settings"));

// The draft is local until Save, so a half-typed number never reaches
// the public page. It is re-seeded whenever the server's answer
// changes, which is on arrival and after a save.
let futureDays = $state(31);
let pastDays = $state(60);
let seeded: unknown = undefined;
$effect(() => {
  const s = query.data;
  if (!s || s === seeded) return;
  seeded = s;
  futureDays = s.agenda_future_days;
  pastDays = s.agenda_past_days;
});

const dirty = $derived(
  !!query.data &&
    (query.data.agenda_future_days !== futureDays || query.data.agenda_past_days !== pastDays),
);

async function submit(event: Event): Promise<void> {
  event.preventDefault();
  try {
    await save.run({ agenda_future_days: futureDays, agenda_past_days: pastDays });
    toasts.success(t("settings.saved"));
  } catch {
    toasts.error(t("settings.saveFailed"));
  }
}
</script>

<AppHeader />
<div class="container-wide stack">
  <h1>{t("settings.title")}</h1>
  <p class="muted">{t("settings.intro")}</p>

  {#if query.isPending}
    <AppSkeleton rows={1} cards />
  {:else}
    <AppCard tag="form" onsubmit={submit}>
      <h2>{t("settings.agendaTitle")}</h2>
      <p class="muted">{t("settings.agendaBody")}</p>

      <!-- An organiser reads the same two numbers as text. A stepper
           they cannot move would only invite the click. -->
      <div class="window-fields">
        <label class="window-field">
          <span>{t("settings.futureDays")}</span>
          {#if canEdit}
            <NumberStepper
              bind:value={futureDays}
              min={MIN_DAYS}
              max={MAX_DAYS}
              ariaLabel={t("settings.futureDays")}
            />
          {:else}
            <strong>{t("settings.days", { n: futureDays })}</strong>
          {/if}
        </label>
        <label class="window-field">
          <span>{t("settings.pastDays")}</span>
          {#if canEdit}
            <NumberStepper
              bind:value={pastDays}
              min={MIN_DAYS}
              max={MAX_DAYS}
              ariaLabel={t("settings.pastDays")}
            />
          {:else}
            <strong>{t("settings.days", { n: pastDays })}</strong>
          {/if}
        </label>
      </div>

      {#if canEdit}
        <div class="save-row">
          <AppButton type="submit" label={t("common.save")} disabled={!dirty} loading={save.pending} />
        </div>
      {:else}
        <p class="muted">{t("settings.readOnly")}</p>
      {/if}
    </AppCard>
  {/if}
</div>

<style>
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
