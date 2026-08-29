<script lang="ts" module>
export interface RecoverableRow {
  id: string;
  name: string | null;
  recoveredAt: string | null;
}
</script>

<script lang="ts">
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
import AppButton from "@/components/AppButton.svelte";
import AppDialog from "@/components/AppDialog.svelte";
import AppPopover from "@/components/AppPopover.svelte";
import { locale, t } from "@/i18n.svelte";
import { post } from "@/api/client";
import { formatDate } from "@/lib/format";
import { tip } from "@/lib/tooltip";
import { useToasts } from "@/lib/toasts";

const {
  count,
  cap,
  label,
  loadRows,
  recoverPath,
  publicUrl,
}: {
  count: number | string;
  /** The ceiling this count runs into, when the account has one. A
   *  personal account holds a bounded number of people per thing it
   *  makes; an organisation has no ceiling, so it passes null and the
   *  pill shows the bare count. */
  cap?: number | null;
  label: string;
  loadRows: () => Promise<RecoverableRow[]>;
  recoverPath: (id: string) => string;
  publicUrl: (token: string) => string;
} = $props();

const toasts = useToasts();

let pop = $state<AppPopover>();
let rows = $state<RecoverableRow[]>([]);
let loading = $state(false);

async function toggle(event: Event) {
  pop?.toggle(event);
  loading = true;
  try {
    rows = await loadRows();
  } catch {
    rows = [];
  } finally {
    loading = false;
  }
}

// Confirm before minting: recovery invalidates the old link and leaves a
// permanent notice on the participant's page, so no silent one-click.
let pending = $state<RecoverableRow | null>(null);
let busy = $state(false);

async function confirmCopy() {
  const row = pending;
  if (!row) return;
  busy = true;
  try {
    const ack = await post<{ edit_token: string }>(recoverPath(row.id));
    await navigator.clipboard.writeText(publicUrl(ack.edit_token));
    row.recoveredAt = new Date().toISOString();
    toasts.success(t("recoverLink.copied"));
  } catch {
    toasts.error(t("recoverLink.failed"));
  } finally {
    busy = false;
    pending = null;
  }
}
</script>

<button type="button" class="count-pill rlp-pill" aria-label={t("recoverLink.open")} onclick={toggle}>
  <span class="count">{cap == null ? count : `${count} / ${cap}`}</span>
  <span class="label">{label}</span>
</button>

<AppPopover bind:this={pop}>
  <div class="rlp-list">
    {#if loading}
      <p class="rlp-muted">{t("common.loading")}</p>
    {:else if rows.length === 0}
      <p class="rlp-muted">{t("recoverLink.empty")}</p>
    {/if}
    {#each rows as row (row.id)}
      <div class="rlp-row">
        <span class="rlp-name">{row.name || t("recoverLink.anonymous")}</span>
        {#if row.recoveredAt}
          <span
            class="rlp-recovered"
            use:tip={t("recoverLink.recoveredOn", { date: formatDate(row.recoveredAt, locale()) })}
            >{t("recoverLink.recoveredMark")}</span
          >
        {/if}
        <span use:tip={t("recoverLink.copy")}>
          <AppButton
            icon="link"
            size="small"
            severity="secondary"
            text
            ariaLabel={t("recoverLink.copy")}
            onclick={() => (pending = row)}
          />
        </span>
      </div>
    {/each}
  </div>
</AppPopover>

<AppDialog
  bind:visible={() => pending !== null, (v) => {
    if (!v) pending = null;
  }}
  header={t("recoverLink.confirmTitle")}
  width="480px"
>
  <p class="rlp-confirm">
    {t("recoverLink.confirmBody", { name: pending?.name || t("recoverLink.anonymous") })}
  </p>
  {#snippet footer()}
    <AppButton
      label={t("common.cancel")}
      size="small"
      severity="secondary"
      text
      disabled={busy}
      onclick={() => (pending = null)}
    />
    <AppButton label={t("recoverLink.confirm")} size="small" loading={busy} onclick={confirmCopy} />
  {/snippet}
</AppDialog>

<style>
/* The pill is a <button> for a11y; neutralise only the UA button chrome
 * that .count-pill doesn't set itself (font/color), so it renders
 * pixel-identical to the read-only pills — border, background, and
 * padding all still come from the shared .count-pill class. */
.rlp-pill {
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: center;
  transition: background 120ms ease, border-color 120ms ease;
}
/* It's a button — say so on hover, like the other clickable rows. */
.rlp-pill:hover {
  background: color-mix(in srgb, var(--brand-red) 7%, var(--brand-bg));
  border-color: color-mix(in srgb, var(--brand-red) 30%, var(--brand-border));
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
