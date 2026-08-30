<script lang="ts">
/**
 * The WhatsApp blast, for admins.
 *
 * Three things on one page: link a number by scanning a code, paste a
 * list of names and numbers, then write one message and send it to all
 * of them.
 *
 * Forgetting when the organiser leaves is wired three ways: the
 * composable's teardown covers navigating away inside the app, the
 * ``pagehide`` below covers a closed tab, and the server's watchdog
 * catches whatever those two miss.
 */
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppDialog from "@/components/AppDialog.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppTextarea from "@/components/AppTextarea.svelte";
import EmojiPicker from "@/components/EmojiPicker.svelte";
import NumberStepper from "@/components/NumberStepper.svelte";
import SelectField from "@/components/SelectField.svelte";
import { whatsApp } from "@/composables/useWhatsApp.svelte";
import { t } from "@/i18n.svelte";
import { COUNTRIES, type Country, flagEmoji } from "@/lib/countries";
import { applyMerge, mergeTags, parseCsv } from "@/lib/csv";
import { whatsappFormat } from "@/lib/whatsappFormat";

const wa = whatsApp();

// --- What survives a reload ------------------------------------------
//
// The list, the message and how far the send got are kept so a long
// disconnect, the kind that forces a fresh scan, or an accidental
// refresh does not lose them. Per tab: ``sessionStorage`` is gone when
// the tab is, which is the same contract the rest of the page keeps.
// Nothing here ever reaches ``localStorage`` or anything shared between
// tabs.
//
// Cleared by the disconnect button and by signing out, so nobody
// inherits the last person's recipients.
const STORAGE_KEY = "opkomst.whatsapp.draft";

interface SendOutcome {
  status: "queued" | "sending" | "sent" | "failed";
  error?: string;
}

interface PersistedState {
  csvText: string;
  phoneColumn: string;
  countryIso: string;
  delaySeconds: number;
  template: string;
  sendResults: Record<string, SendOutcome>;
}

function readPersisted(): Partial<PersistedState> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<PersistedState>) : {};
  } catch {
    return {};
  }
}

function clearPersisted(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode or a full quota; not worth reacting to */
  }
}

const persisted = readPersisted();

// --- The recipients ---------------------------------------------------
let csvText = $state(persisted.csvText ?? "");
let phoneColumn = $state(persisted.phoneColumn ?? "nummer");
/** The country code put in front of a bare national number, so
 *  ``0612345678`` becomes ``31612345678``. The Netherlands by default,
 *  because that is overwhelmingly what this is used for. */
let country = $state<Country>(
  COUNTRIES.find((c) => c.iso === (persisted.countryIso ?? "NL")) ?? COUNTRIES[0],
);

const parsed = $derived(parseCsv(csvText, phoneColumn, country.dialCode));
const validRows = $derived(parsed.rows.filter((r) => r.status === "ok"));
const tags = $derived(mergeTags(parsed.headers, phoneColumn));

// --- The message ------------------------------------------------------
let template = $state(persisted.template ?? "");
/** The real textarea, so an emoji can go in at the caret. */
let composeField = $state<HTMLTextAreaElement>();
let sending = $state(false);
let paused = $state(false);
let cancelled = $state(false);
let currentLine = $state<number | null>(null);

/**
 * What happened to each recipient, keyed by the cleaned-up number.
 *
 * By number and not by line, so picking up after a reconnect survives
 * the list being reordered, a row being deleted, or the whole thing
 * being pasted again: those change line numbers but not people.
 *
 * Only rows already sent are restored. Anything queued, sending or
 * failed when the tab went down is tried again on the next send, since
 * a failure there is usually a passing one.
 */
let sendResults = $state<Record<string, SendOutcome>>(
  Object.fromEntries(
    Object.entries(persisted.sendResults ?? {}).filter(([, v]) => v.status === "sent"),
  ),
);

const sentCount = $derived(Object.values(sendResults).filter((r) => r.status === "sent").length);
const failedCount = $derived(
  Object.values(sendResults).filter((r) => r.status === "failed").length,
);
const progress = $derived(
  validRows.length === 0
    ? 0
    : Math.round(((sentCount + failedCount) / validRows.length) * 100),
);
const finished = $derived(
  validRows.length > 0 && sentCount + failedCount === validRows.length,
);

// How long to wait between sends. Six seconds is the middle of what
// WhatsApp tolerates from a freshly linked device. Two is the floor:
// below it the server starts warning about the pace and the link is at
// risk. The ceiling is there to catch a typo.
const DELAY_MIN = 2;
const DELAY_MAX = 60;
let delaySeconds = $state(persisted.delaySeconds ?? 6);

const previewSourceRow = $derived(validRows[0] ?? null);
const previewMerged = $derived(
  previewSourceRow ? applyMerge(template, previewSourceRow.fields) : template,
);
const previewHtml = $derived(whatsappFormat(previewMerged));

const sendDisabled = $derived(
  sending || finished || validRows.length === 0 || template.trim() === "",
);
const hasPersistedProgress = $derived(
  csvText.trim() !== "" || Object.keys(sendResults).length > 0,
);

// Mirrored on every change.
$effect(() => {
  const snapshot: PersistedState = {
    csvText,
    phoneColumn,
    countryIso: country.iso,
    delaySeconds,
    template,
    sendResults: $state.snapshot(sendResults),
  };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    /* private mode or a full quota: what is in memory still drives the
     * page */
  }
});

function clearAllProgress(): void {
  csvText = "";
  template = "";
  sendResults = {};
  cancelled = false;
  paused = false;
  currentLine = null;
  clearPersisted();
}

/** Disconnecting also wipes the draft: it is somebody saying they are
 *  done with this blast, and the list would otherwise outlive the link
 *  it was for. */
async function onDisconnect(): Promise<void> {
  clearAllProgress();
  await wa.disconnect();
}

function insertEmoji(emoji: string): void {
  // At the caret, or on the end when the field has never been focused
  // and so has no caret to speak of.
  const ta = composeField;
  if (!ta) {
    template += emoji;
    return;
  }
  const start = ta.selectionStart ?? template.length;
  const end = ta.selectionEnd ?? template.length;
  template = template.slice(0, start) + emoji + template.slice(end);
  // Put the caret back once the field has been redrawn with the new
  // value.
  queueMicrotask(() => {
    ta.focus();
    const pos = start + emoji.length;
    ta.setSelectionRange(pos, pos);
  });
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Twenty per cent either side of the chosen pace. A perfectly regular
 *  cadence is what a bot looks like; this is not one. */
function nextDelayMs(): number {
  return delaySeconds * 1000 * (0.8 + Math.random() * 0.4);
}

/** Wait for the link to come back, or for a cancel or the deadline.
 *  True means it is back and the row can be tried again. */
async function awaitReconnect(timeoutMs = 60_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (!cancelled && wa.state !== "open" && Date.now() < deadline) {
    await sleep(2_000);
  }
  return wa.state === "open" && !cancelled;
}

async function runSendLoop(): Promise<void> {
  sending = true;
  cancelled = false;
  paused = false;

  // What was already sent stays sent, and is skipped below, so a
  // re-link picks up exactly where the blast stopped. Everything else
  // gets a fresh attempt.
  for (const phone of Object.keys(sendResults)) {
    if (sendResults[phone]?.status !== "sent") delete sendResults[phone];
  }

  for (const row of validRows) {
    if (cancelled) break;
    while (paused && !cancelled) await sleep(250);
    if (cancelled) break;
    if (sendResults[row.phone]?.status === "sent") continue;

    currentLine = row.line;

    // WhatsApp tears linked-device sessions down regularly and the
    // client is back within seconds. Those moments must not burn a
    // recipient, so the row waits and is tried again. Three attempts,
    // so a session that is really broken cannot spin here forever.
    let done = false;
    for (let attempt = 0; attempt < 3 && !done && !cancelled; attempt++) {
      if (wa.state !== "open") {
        sendResults[row.phone] = { status: "queued" };
        if (!(await awaitReconnect())) break;
      }
      sendResults[row.phone] = { status: "sending" };
      const res = await wa.send(row.phone, applyMerge(template, row.fields));
      if (res.ok) {
        sendResults[row.phone] = { status: "sent" };
        done = true;
      } else if (wa.state !== "open") {
        // The link dropped during the send; the next turn retries it.
        continue;
      } else {
        // The link is fine, so this is about this recipient: the number
        // is not on WhatsApp, say. Trying again would not help.
        sendResults[row.phone] = { status: "failed", error: res.error };
        done = true;
      }
    }
    if (!done && !cancelled) {
      sendResults[row.phone] = { status: "failed", error: "could not reconnect within 60s" };
    }

    if (row !== validRows[validRows.length - 1]) await sleep(nextDelayMs());
  }

  currentLine = null;
  sending = false;
}

let confirmOpen = $state(false);

function acceptConfirm(): void {
  confirmOpen = false;
  void runSendLoop();
}

function cancelSend(): void {
  cancelled = true;
  paused = false;
}

/** The list as it arrived, plus what happened to each row. Only the
 *  rows that were actually going to be sent to. */
function downloadResults(): void {
  const cols = [...parsed.headers, "send_status", "send_error"];
  const escape = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const lines = [cols.join(",")];
  for (const row of validRows) {
    const result = sendResults[row.phone];
    const cells = parsed.headers.map((h) => escape(row.fields[h] ?? ""));
    cells.push(escape(result?.status ?? ""));
    cells.push(escape(result?.error ?? ""));
    lines.push(cells.join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "whatsapp-blast-results.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function onPageHide(): void {
  // A beacon is the only shape of request that survives a closing tab.
  // If it fails, or is not supported, the watchdog has it within the
  // minute anyway.
  try {
    const blob = new Blob([JSON.stringify({})], { type: "application/json" });
    navigator.sendBeacon("/api/v1/whatsapp/logout", blob);
  } catch {
    /* nothing useful to do here */
  }
}

/** Browsers ignore anything written here, but asking at all gets their
 *  own "leave site?" prompt, which is enough to stop a tab being closed
 *  in the middle of a blast. */
function onBeforeUnload(e: BeforeUnloadEvent): void {
  if (!sending) return;
  e.preventDefault();
  e.returnValue = "";
}

$effect(() => {
  wa.startPolling();
  window.addEventListener("pagehide", onPageHide);
  window.addEventListener("beforeunload", onBeforeUnload);
  return () => {
    window.removeEventListener("pagehide", onPageHide);
    window.removeEventListener("beforeunload", onBeforeUnload);
  };
});
</script>

<AppHeader />
<div class="container-wide wa-container stack">
  <h1>{t("whatsapp.title")}</h1>
  <p class="muted">{t("whatsapp.lede")}</p>

  <AppCard class="wa-card">
    <!-- The code to scan while there is no link, a slim row once there
         is one. -->
    {#if wa.stableState !== "open" && wa.stableState !== "not_configured"}
      <div class="connect">
        <h2>{t("whatsapp.connect.title")}</h2>
        <ol class="instructions">
          <li>{t("whatsapp.connect.step1")}</li>
          <li>{t("whatsapp.connect.step2")}</li>
          <li>{t("whatsapp.connect.step3")}</li>
        </ol>
        <div class="qr-wrap">
          {#if wa.qr}
            <img src={wa.qr} alt={t("whatsapp.connect.qrAlt")} class="qr" />
          {:else}
            <div class="qr-loading">{t("common.loading")}</div>
          {/if}
        </div>
        {#if wa.pairingCode}
          <p class="pairing">
            {t("whatsapp.connect.pairingCode")}
            <code>{wa.pairingCode}</code>
          </p>
        {/if}
        <p class="status-line">
          {t("whatsapp.connect.statusLabel")}
          <strong>{t(`whatsapp.state.${wa.state}`)}</strong>
        </p>
      </div>
    {:else if wa.stableState === "open"}
      <div class="linked">
        <span class="linked-pill">
          ✓ {t("whatsapp.connected.linked")}
          {#if wa.reconnecting}
            <span class="reconnect-note">({t("whatsapp.connected.reconnecting")})</span>
          {/if}
        </span>
        <AppButton
          label={t("whatsapp.connected.disconnect")}
          severity="secondary"
          text
          class="disconnect-btn"
          onclick={onDisconnect}
        />
      </div>
    {/if}

    <!-- The recipients and the message, once there is a link. No step
         numbering: the page is short enough to read top to bottom. -->
    {#if wa.stableState === "open"}
      <h2 class="section-h">{t("whatsapp.recipients.title")}</h2>
      <p class="muted">{t("whatsapp.recipients.hint")}</p>

      <div class="phone-config">
        <label class="phone-col">
          <span>{t("whatsapp.recipients.phoneColumnLabel")}</span>
          <AppInput
            bind:value={phoneColumn}
            spellcheck={false}
            autocomplete="off"
            class="phone-col-input"
          />
        </label>
        <label class="phone-col">
          <span>{t("whatsapp.recipients.countryCodeLabel")}</span>
          <SelectField
            bind:value={country}
            options={COUNTRIES}
            optionLabel="name"
            filter
            filterPlaceholder="..."
            class="country-select"
          >
            {#snippet valueSnippet({ value })}
              {#if value}
                <span class="country-row">
                  <span class="flag">{flagEmoji(value.iso)}</span>
                  <span>+{value.dialCode}</span>
                </span>
              {/if}
            {/snippet}
            {#snippet optionSnippet({ option })}
              <span class="country-row">
                <span class="flag">{flagEmoji(option.iso)}</span>
                <span class="country-name">{option.name}</span>
                <span class="country-dial">+{option.dialCode}</span>
              </span>
            {/snippet}
          </SelectField>
        </label>
      </div>

      <AppTextarea bind:value={csvText} rows={8} class="csv-textarea" />

      {#if parsed.fatal.length}
        <div class="fatal">
          {#each parsed.fatal as code (code)}
            <p>{t(`whatsapp.recipients.errors.${code}`)}</p>
          {/each}
        </div>
      {/if}

      {#if parsed.headers.length}
        <div class="parse-summary">
          <p class="counts">
            <strong>{validRows.length}</strong>
            {t("whatsapp.recipients.validCount")}
            {#if parsed.rows.length - validRows.length > 0}
              ,
              <strong>{parsed.rows.length - validRows.length}</strong>
              {t("whatsapp.recipients.invalidCount")}
            {/if}
            {#if sentCount > 0}
              · <strong>{sentCount}</strong>
              {t("whatsapp.recipients.alreadySent")}
            {/if}
          </p>
          {#if tags.length}
            <p class="tags">
              {t("whatsapp.recipients.availableTags")}
              {#each tags as tag (tag)}
                <code class="tag">{`{${tag}}`}</code>
              {/each}
            </p>
          {/if}
          {#if hasPersistedProgress && !sending}
            <AppButton
              label={t("whatsapp.recipients.clear")}
              severity="secondary"
              size="small"
              text
              onclick={clearAllProgress}
            />
          {/if}
        </div>
      {/if}

      {#if parsed.rows.length}
        <div class="preview-table-wrap">
          <table class="preview-table">
            <thead>
              <tr>
                <th>#</th>
                {#each parsed.headers as h (h)}<th>{h}</th>{/each}
                <th>{t("whatsapp.recipients.status")}</th>
              </tr>
            </thead>
            <tbody>
              {#each parsed.rows as row, idx (idx)}
                <tr class:invalid={row.status === "invalid"}>
                  <td>{idx + 1}</td>
                  {#each parsed.headers as h (h)}
                    <td>
                      {h === phoneColumn.toLowerCase() ? row.phone || row.fields[h] : row.fields[h]}
                    </td>
                  {/each}
                  <td>
                    {#if row.status === "ok"}
                      <span class="ok">✓</span>
                    {:else}
                      <span class="bad">✗ {t(`whatsapp.recipients.errors.${row.error}`)}</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}

      <h2 class="section-h">{t("whatsapp.compose.title")}</h2>
      <p class="muted">{t("whatsapp.compose.hint")}</p>

      <div class="compose-grid">
        <div class="compose-input">
          <AppTextarea
            bind:value={template}
            bind:element={composeField}
            rows={8}
            placeholder={t("whatsapp.compose.placeholder")}
            class="compose-textarea"
            autoResize
            disabled={sending}
          />
          <div class="compose-toolbar">
            <EmojiPicker onselect={insertEmoji} />
            <span class="fmt"
              ><code>*</code><strong>{t("whatsapp.compose.bold")}</strong><code>*</code></span
            >
            <span class="fmt"><code>_</code><em>{t("whatsapp.compose.italic")}</em><code>_</code></span>
            <span class="fmt"><code>~</code><s>{t("whatsapp.compose.strike")}</s><code>~</code></span>
            <span class="fmt"><code>`{t("whatsapp.compose.mono")}`</code></span>
          </div>
        </div>

        <div class="compose-preview">
          <div class="preview-bubble">
            {#if !previewMerged}
              <span class="preview-empty">{t("whatsapp.compose.previewEmpty")}</span>
            {:else}
              <span>{@html previewHtml}</span>
            {/if}
          </div>
        </div>
      </div>

      {#if !sending && !finished}
        <div class="delay-row">
          <label class="delay-label">
            <span>{t("whatsapp.compose.delayLabel")}</span>
            <NumberStepper
              bind:value={delaySeconds}
              min={DELAY_MIN}
              max={DELAY_MAX}
              suffix="s"
              ariaLabel={t("whatsapp.compose.delayLabel")}
            />
          </label>
          <p class="muted delay-hint">{t("whatsapp.compose.delayHint")}</p>
        </div>
      {/if}

      {#if sending || finished}
        <div class="send-progress">
          <div
            class="progress"
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div class="progress-fill" style:width={`${progress}%`}></div>
          </div>
          <p class="progress-line">
            {sentCount}
            {t("whatsapp.compose.sent")},
            {failedCount}
            {t("whatsapp.compose.failed")}
            {#if !finished}
              ({t("whatsapp.compose.of", { total: validRows.length })})
            {/if}
          </p>
        </div>
      {/if}

      {#if sending}
        <p class="closing-warning">⚠️ {t("whatsapp.compose.dontCloseWarning")}</p>
      {/if}

      <div class="send-controls">
        {#if !sending && !finished}
          <AppButton
            label={t("whatsapp.compose.sendButton", { count: validRows.length })}
            disabled={sendDisabled}
            onclick={() => (confirmOpen = true)}
          />
        {/if}
        {#if sending}
          {#if !paused}
            <AppButton
              label={t("whatsapp.compose.pause")}
              severity="secondary"
              onclick={() => (paused = true)}
            />
          {:else}
            <AppButton label={t("whatsapp.compose.resume")} onclick={() => (paused = false)} />
          {/if}
          <AppButton
            label={t("whatsapp.compose.cancel")}
            severity="danger"
            text
            onclick={cancelSend}
          />
        {/if}
      </div>

      {#if Object.keys(sendResults).length}
        <div class="send-table-wrap">
          <table class="preview-table">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("whatsapp.recipients.status")}</th>
                {#each parsed.headers as h (h)}<th>{h}</th>{/each}
                <th>{t("whatsapp.compose.sendStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {#each validRows as row, idx (row.line)}
                <tr
                  class:send-current={currentLine === row.line}
                  class:send-failed={sendResults[row.phone]?.status === "failed"}
                  class:send-sent={sendResults[row.phone]?.status === "sent"}
                >
                  <td>{idx + 1}</td>
                  <td><span class="ok">✓</span></td>
                  {#each parsed.headers as h (h)}
                    <td>
                      {h === phoneColumn.toLowerCase() ? row.phone || row.fields[h] : row.fields[h]}
                    </td>
                  {/each}
                  <td>
                    {#if sendResults[row.phone]?.status === "sent"}
                      <span class="ok">✓ {t("whatsapp.compose.sent")}</span>
                    {:else if sendResults[row.phone]?.status === "failed"}
                      <span class="bad">
                        ✗ {sendResults[row.phone]?.error || t("whatsapp.compose.failed")}
                      </span>
                    {:else if sendResults[row.phone]?.status === "sending"}
                      <span class="sending-cell">…</span>
                    {:else}
                      <span class="muted">-</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}

      {#if finished}
        <div class="download-row">
          <AppButton
            label={t("whatsapp.compose.download")}
            severity="secondary"
            onclick={downloadResults}
          />
        </div>
      {/if}
    {/if}
  </AppCard>

  <AppDialog bind:visible={confirmOpen} header={t("whatsapp.compose.confirmHeader")}>
    <p class="confirm-lead">
      {t("whatsapp.compose.confirmLead", { count: validRows.length })}
    </p>
    <div class="preview-bubble confirm-bubble">
      {#if !previewMerged}
        <span class="preview-empty">{t("whatsapp.compose.previewEmpty")}</span>
      {:else}
        <span>{@html previewHtml}</span>
      {/if}
    </div>
    {#snippet footer()}
      <AppButton
        label={t("common.cancel")}
        severity="secondary"
        text
        onclick={() => (confirmOpen = false)}
      />
      <AppButton
        label={t("whatsapp.compose.confirmAccept", { count: validRows.length })}
        onclick={acceptConfirm}
      />
    {/snippet}
  </AppDialog>
</div>

<style>
/* Wider than the app's usual column: the compose pane is genuinely two
 * columns, and the recipients table wants the room. */
.wa-container {
  max-width: 64rem;
}

/* The whole flow is one card, so the air between its parts comes from
 * the headings rather than from card edges. */
:global(.wa-card > * + *) {
  margin-top: 1rem;
}
.section-h {
  margin-top: 2rem;
}

/* --- Linking --------------------------------------------------- */
.connect h2 {
  margin-bottom: 0.75rem;
}
.instructions {
  margin: 0 0 1rem 1.25rem;
  padding: 0;
  line-height: 1.6;
}
.linked {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.linked :global(.disconnect-btn) {
  margin-left: auto;
}
.linked-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  background: var(--brand-green-soft);
  color: var(--brand-green);
  border: 1px solid var(--brand-green-soft-border);
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
}
.qr-wrap {
  display: flex;
  justify-content: center;
  margin: 1rem 0;
  min-height: 256px;
  align-items: center;
}
.qr {
  width: 256px;
  height: 256px;
  image-rendering: pixelated;
  background: white;
  padding: 0.5rem;
  border-radius: 10px;
  border: 1px solid var(--brand-border);
}
.qr-loading {
  color: var(--brand-text-muted);
}
.pairing {
  text-align: center;
  margin: 0.5rem 0 0;
  font-size: 0.875rem;
}
.pairing code {
  padding: 0.1rem 0.4rem;
  background: var(--brand-bg);
  border-radius: 0.25rem;
  letter-spacing: 0.1em;
}
.status-line {
  text-align: center;
  margin-top: 0.5rem;
  color: var(--brand-text-muted);
  font-size: 0.875rem;
}

/* --- The recipients -------------------------------------------- */
.phone-config {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}
.phone-col {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
.phone-col :global(.phone-col-input) {
  max-width: 12rem;
}
.phone-col :global(.country-select) {
  min-width: 8rem;
}
.country-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}
.country-row .flag {
  font-size: 1.125rem;
  line-height: 1;
}
.country-row .country-name {
  flex: 1;
}
.country-row .country-dial {
  color: var(--brand-text-muted);
  font-variant-numeric: tabular-nums;
}
/* The height is fixed, so a big paste scrolls inside the box instead of
 * pushing the rest of the page down, and the corner cannot be
 * dragged. */
.wa-container :global(.csv-textarea) {
  width: 100%;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.875rem;
  resize: none;
  overflow: auto;
}
.download-row {
  display: flex;
  justify-content: flex-end;
}
.fatal {
  color: var(--brand-red);
}
.parse-summary {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.counts,
.tags {
  margin: 0;
  font-size: 0.875rem;
}
.tags {
  color: var(--brand-text-muted);
}
.tag {
  display: inline-block;
  margin-left: 0.25rem;
  padding: 0.05rem 0.4rem;
  background: var(--brand-bg);
  border: 1px solid var(--brand-border);
  border-radius: 0.25rem;
  color: var(--brand-text);
}
.preview-table-wrap,
.send-table-wrap {
  max-height: 24rem;
  overflow: auto;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
}
.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
.preview-table th,
.preview-table td {
  padding: 0.4rem 0.6rem;
  text-align: left;
  border-bottom: 1px solid var(--brand-border);
}
.preview-table th {
  position: sticky;
  top: 0;
  background: var(--brand-bg);
  z-index: 1;
}
.preview-table tr.invalid {
  background: var(--brand-red-wash);
}
.preview-table .ok {
  color: var(--brand-green);
}
.preview-table .bad {
  color: var(--brand-red);
}

/* --- The message ----------------------------------------------- */
.compose-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
@media (max-width: 720px) {
  .compose-grid {
    grid-template-columns: 1fr;
  }
}
.compose-input {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.compose-input :global(.compose-textarea) {
  width: 100%;
  font-size: 0.875rem;
}
.compose-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin: -0.25rem 0 0.25rem;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}
.fmt code {
  background: var(--brand-bg);
  padding: 0 0.15rem;
  border-radius: 0.2rem;
}
/* WhatsApp's own bubble colour, on purpose: the point of the preview is
 * to show what the person on the other end will see, so the green is
 * fidelity rather than a brand choice. */
.preview-bubble {
  background: var(--brand-chat-bubble);
  color: var(--brand-chat-text);
  padding: 0.75rem 1rem;
  border-radius: 0.75rem 0.75rem 0.75rem 0.25rem;
  min-height: 4rem;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 0.875rem;
  line-height: 1.4;
}
.preview-empty {
  color: var(--brand-text-muted);
  font-style: italic;
}
.confirm-lead {
  margin: 0 0 0.75rem;
}
.confirm-bubble {
  max-height: 18rem;
  overflow-y: auto;
}
/* The send bar. One call site, so it stays here rather than becoming a
 * component with a single consumer. */
.progress {
  height: 1.125rem;
  background: var(--brand-surface-200);
  border-radius: 6px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--brand-primary-500);
  transition: width 0.2s;
}
.progress-line {
  margin: 0.5rem 0 0;
  font-size: 0.875rem;
  color: var(--brand-text-muted);
}
.send-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.delay-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}
.delay-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
.delay-hint {
  font-size: 0.8125rem;
  margin: 0;
  flex-basis: 100%;
}
.closing-warning {
  background: var(--brand-amber-soft);
  border: 1px solid var(--brand-amber-soft-border);
  color: var(--brand-amber-strong);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  margin: 0;
  font-size: 0.875rem;
}
.send-current {
  background: var(--brand-bg);
}
.send-sent .ok {
  color: var(--brand-green);
}
.send-failed .bad {
  color: var(--brand-red);
}
.sending-cell,
.muted {
  color: var(--brand-text-muted);
}
</style>
