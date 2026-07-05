<script setup lang="ts">
/**
 * The clickable participants pill — shared magic-link recovery across
 * all four entities (event signups, form/datepoll submissions, chore
 * volunteers). Clicking the count pill opens a popover listing every
 * participant with a copy-link button. Copying re-mints the secret
 * edit link (the server only stores a hash, so recovery rotates: the
 * old link dies) and permanently stamps the row, which the public edit
 * page discloses with a banner — hence the confirm step first.
 *
 * Pages stay thin: they hand in the pill count/label, a lazy row
 * loader, the recover endpoint path, and the public URL builder.
 */
import Button from "primevue/button";
import Popover from "primevue/popover";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import AppDialog from "@/components/AppDialog.vue";
import { post } from "@/api/client";
import { useToasts } from "@/lib/toasts";
import { formatDate } from "@/lib/format";

export interface RecoverableRow {
  id: string;
  name: string | null;
  recoveredAt: string | null;
}

const props = defineProps<{
  count: number | string;
  label: string;
  loadRows: () => Promise<RecoverableRow[]>;
  recoverPath: (id: string) => string;
  publicUrl: (token: string) => string;
}>();

const { t, locale } = useI18n();
const toasts = useToasts();

const pop = ref<InstanceType<typeof Popover>>();
const rows = ref<RecoverableRow[]>([]);
const loading = ref(false);

async function toggle(event: Event) {
  pop.value?.toggle(event);
  loading.value = true;
  try {
    rows.value = await props.loadRows();
  } catch {
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

// Confirm-before-mint: recovery invalidates the old link and leaves a
// permanent notice on the participant's page, so no silent one-click.
const pending = ref<RecoverableRow | null>(null);
const busy = ref(false);

async function confirmCopy() {
  const row = pending.value;
  if (!row) return;
  busy.value = true;
  try {
    const ack = await post<{ edit_token: string }>(props.recoverPath(row.id));
    const url = props.publicUrl(ack.edit_token);
    await navigator.clipboard.writeText(url);
    row.recoveredAt = new Date().toISOString();
    toasts.success(t("recoverLink.copied"));
    // Jump straight to the participant's fresh edit page (new tab, so
    // the organiser keeps their place) — lets them eyeball or hand over
    // the open page directly.
    window.open(url, "_blank", "noopener");
  } catch {
    toasts.error(t("recoverLink.failed"));
  } finally {
    busy.value = false;
    pending.value = null;
  }
}
</script>

<template>
  <button type="button" class="count-pill rlp-pill" :aria-label="t('recoverLink.open')" @click="toggle">
    <span class="count">{{ count }}</span>
    <span class="label">{{ label }}</span>
  </button>

  <Popover ref="pop">
    <div class="rlp-list">
      <p v-if="loading" class="rlp-muted">{{ t("common.loading") }}</p>
      <p v-else-if="rows.length === 0" class="rlp-muted">{{ t("recoverLink.empty") }}</p>
      <div v-for="row in rows" :key="row.id" class="rlp-row">
        <span class="rlp-name">{{ row.name || t("recoverLink.anonymous") }}</span>
        <span
          v-if="row.recoveredAt"
          class="rlp-recovered"
          v-tooltip.top="t('recoverLink.recoveredOn', { date: formatDate(row.recoveredAt, locale) })"
          >{{ t("recoverLink.recoveredMark") }}</span
        >
        <Button
          icon="pi pi-link"
          size="small"
          severity="secondary"
          text
          :aria-label="t('recoverLink.copy')"
          v-tooltip.top="t('recoverLink.copy')"
          @click="pending = row"
        />
      </div>
    </div>
  </Popover>

  <AppDialog
    :visible="pending !== null"
    :header="t('recoverLink.confirmTitle')"
    width="480px"
    @update:visible="(v: boolean) => (v ? undefined : (pending = null))"
  >
    <p class="rlp-confirm">{{ t("recoverLink.confirmBody", { name: pending?.name || t("recoverLink.anonymous") }) }}</p>
    <template #footer>
      <Button
        :label="t('common.cancel')"
        size="small"
        severity="secondary"
        text
        :disabled="busy"
        @click="pending = null"
      />
      <Button :label="t('recoverLink.confirm')" size="small" :loading="busy" @click="confirmCopy" />
    </template>
  </AppDialog>
</template>

<style scoped>
/* The pill is a <button> for a11y; neutralise only the UA button chrome
 * that .count-pill doesn't set itself (font/color), so it renders
 * pixel-identical to the read-only pills — border, background, and
 * padding all still come from the shared .count-pill class. */
.rlp-pill {
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: center;
}
.rlp-list {
  min-width: 16rem;
  max-width: 22rem;
  max-height: 20rem;
  overflow-y: auto;
  /* Keep the scrollbar off the per-row copy buttons. */
  padding-right: 0.75rem;
  scrollbar-gutter: stable;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.rlp-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.125rem 0.375rem;
  border-radius: 6px;
}
/* Row highlight on hover, so it's clear whose link you're about to copy. */
.rlp-row:hover {
  background: color-mix(in srgb, var(--brand-red) 7%, transparent);
}
.rlp-name {
  flex: 1 1 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rlp-recovered {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
}
.rlp-muted {
  margin: 0;
  color: var(--brand-text-muted);
  font-size: 0.875rem;
}
.rlp-confirm {
  margin: 0;
}
</style>
