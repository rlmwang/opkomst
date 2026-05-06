<script setup lang="ts">
/**
 * Admin-only WhatsApp blast tool.
 *
 * Three sections, in one page:
 *  A. Connect. scan QR to link a WhatsApp number to the
 *     server-side Evolution instance.
 *  B. Recipients. paste/upload a name+phone list (next step).
 *  C. Compose & send. type a message with {name} merge and
 *     send it through the linked session (next step).
 *
 * "Forget on leave" is wired three ways:
 *  - ``onBeforeUnmount`` in the composable (SPA nav away).
 *  - ``pagehide`` listener below (browser tab close).
 *  - Server-side watchdog catches anything those two miss.
 */
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import ProgressBar from "primevue/progressbar";
import Textarea from "primevue/textarea";
import { computed, ref } from "vue";
import { onBeforeUnmount, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import EmojiPicker from "@/components/EmojiPicker.vue";
import { useWhatsApp } from "@/composables/useWhatsApp";
import { useConfirms } from "@/lib/confirms";
import { applyMerge, mergeTags, parseCsv } from "@/lib/csv";
import { whatsappFormat } from "@/lib/whatsappFormat";

const { t } = useI18n();
const wa = useWhatsApp();
const confirms = useConfirms();

// Section B state. Kept in the page (not the composable) since
// it's purely client-side and doesn't outlive the page mount.
const csvText = ref("");
const phoneColumn = ref("number");
// Default country code applied to bare national numbers in the
// CSV (e.g. ``0612345678`` becomes ``31612345678``). Defaults to
// NL since that's the overwhelmingly common case for this app;
// the user can clear or change it.
const countryCode = ref("31");
const parsed = computed(() =>
  parseCsv(csvText.value, phoneColumn.value, countryCode.value),
);
const validRows = computed(() => parsed.value.rows.filter((r) => r.status === "ok"));
const tags = computed(() => mergeTags(parsed.value.headers, phoneColumn.value));

// Section C state. ``template`` is the message body; the send
// loop below walks ``validRows`` and writes results into
// ``sendResults`` so the parser's per-row state isn't disturbed
// (rows can be re-validated mid-blast if the CSV is edited).
const template = ref("");
// Ref to the PrimeVue Textarea so the emoji picker can insert at
// the cursor position. PrimeVue exposes the underlying DOM
// element on ``$el``.
const composeRef = ref<{ $el: HTMLTextAreaElement } | null>(null);
const sending = ref(false);
const paused = ref(false);
const cancelled = ref(false);
const currentLine = ref<number | null>(null);
type SendOutcome = { status: "queued" | "sending" | "sent" | "failed"; error?: string };
const sendResults = ref<Record<number, SendOutcome>>({});
const sentCount = computed(
  () => Object.values(sendResults.value).filter((r) => r.status === "sent").length,
);
const failedCount = computed(
  () => Object.values(sendResults.value).filter((r) => r.status === "failed").length,
);
const progress = computed(() => {
  const total = validRows.value.length;
  if (total === 0) return 0;
  return Math.round(((sentCount.value + failedCount.value) / total) * 100);
});
const finished = computed(
  () => validRows.value.length > 0 && sentCount.value + failedCount.value === validRows.value.length,
);

const previewSourceRow = computed(() => validRows.value[0] ?? null);
const previewMerged = computed(() =>
  previewSourceRow.value ? applyMerge(template.value, previewSourceRow.value.fields) : template.value,
);
const previewHtml = computed(() => whatsappFormat(previewMerged.value));

const sendDisabled = computed(
  () => sending.value || finished.value || validRows.value.length === 0 || template.value.trim() === "",
);

function insertEmoji(emoji: string): void {
  // Insert at the current selection; if the textarea has never
  // been focused (no selection), append. Native ``input`` event
  // is dispatched so the v-model picks it up.
  const ta = composeRef.value?.$el;
  if (!ta) {
    template.value = template.value + emoji;
    return;
  }
  const start = ta.selectionStart ?? template.value.length;
  const end = ta.selectionEnd ?? template.value.length;
  const next = template.value.slice(0, start) + emoji + template.value.slice(end);
  template.value = next;
  // Restore the cursor on the next tick once Vue has re-rendered
  // the textarea's value.
  queueMicrotask(() => {
    ta.focus();
    const pos = start + emoji.length;
    ta.setSelectionRange(pos, pos);
  });
}

function jitter(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function runSendLoop(): Promise<void> {
  sending.value = true;
  cancelled.value = false;
  paused.value = false;
  sendResults.value = {};

  for (const row of validRows.value) {
    if (cancelled.value) break;
    while (paused.value && !cancelled.value) {
      await sleep(250);
    }
    if (cancelled.value) break;

    currentLine.value = row.line;
    sendResults.value[row.line] = { status: "sending" };
    const text = applyMerge(template.value, row.fields);
    const res = await wa.send(row.phone, text);
    sendResults.value[row.line] = res.ok
      ? { status: "sent" }
      : { status: "failed", error: res.error };
    // Pace between sends with random jitter to keep the spam-detection
    // heuristic at bay. Skip after the last send.
    if (row !== validRows.value[validRows.value.length - 1]) {
      await sleep(jitter(4000, 9000));
    }
  }

  currentLine.value = null;
  sending.value = false;
}

function confirmSend(): void {
  confirms.ask({
    header: t("whatsapp.compose.confirmHeader"),
    message: t("whatsapp.compose.confirmMessage", {
      count: validRows.value.length,
      preview: previewMerged.value.slice(0, 200),
    }),
    acceptLabel: t("whatsapp.compose.confirmAccept", { count: validRows.value.length }),
    rejectLabel: t("common.cancel"),
    accept: () => {
      void runSendLoop();
    },
  });
}

function cancelSend(): void {
  cancelled.value = true;
  paused.value = false;
}

function downloadResults(): void {
  // CSV with the source headers + send_status + send_error,
  // ordered the way the rows arrived (skipping invalid ones so
  // the export only contains rows the user actually intended to
  // send).
  const cols = [...parsed.value.headers, "send_status", "send_error"];
  const escape = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const lines = [cols.join(",")];
  for (const row of validRows.value) {
    const result = sendResults.value[row.line];
    const cells = parsed.value.headers.map((h) => escape(row.fields[h] ?? ""));
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

function onFile(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    csvText.value = String(reader.result ?? "");
  };
  reader.readAsText(file);
}

function onPageHide(): void {
  // Best-effort: ``sendBeacon`` is the only request shape that
  // survives a tab close. Failures (or beacon being unsupported)
  // are fine. the server watchdog tears the session down within
  // a minute anyway.
  try {
    const blob = new Blob([JSON.stringify({})], { type: "application/json" });
    navigator.sendBeacon("/api/v1/whatsapp/logout", blob);
  } catch {
    /* nothing useful to do here */
  }
}

onMounted(() => {
  wa.startPolling();
  window.addEventListener("pagehide", onPageHide);
});

onBeforeUnmount(() => {
  window.removeEventListener("pagehide", onPageHide);
});
</script>

<template>
  <AppHeader />
  <div class="container wa-container stack">
    <h1>{{ t("whatsapp.title") }}</h1>
    <p class="muted">{{ t("whatsapp.lede") }}</p>

    <!-- Section A: Connect -->
    <AppCard
      v-if="wa.state.value !== 'open' && wa.state.value !== 'not_configured'"
      class="connect-card"
    >
      <h2>{{ t("whatsapp.connect.title") }}</h2>
      <ol class="instructions">
        <li>{{ t("whatsapp.connect.step1") }}</li>
        <li>{{ t("whatsapp.connect.step2") }}</li>
        <li>{{ t("whatsapp.connect.step3") }}</li>
      </ol>

      <div class="qr-wrap">
        <img
          v-if="wa.qr.value"
          :src="wa.qr.value"
          :alt="t('whatsapp.connect.qrAlt')"
          class="qr"
        />
        <div v-else class="qr-loading">{{ t("common.loading") }}</div>
      </div>

      <p v-if="wa.pairingCode.value" class="pairing">
        {{ t("whatsapp.connect.pairingCode") }}
        <code>{{ wa.pairingCode.value }}</code>
      </p>

      <p class="status-line">
        {{ t("whatsapp.connect.statusLabel") }}
        <strong>{{ t(`whatsapp.state.${wa.state.value}`) }}</strong>
      </p>
    </AppCard>

    <!-- Section A (connected variant): linked number + disconnect -->
    <AppCard v-if="wa.state.value === 'open'" class="connected-card">
      <h2>{{ t("whatsapp.connected.title") }}</h2>
      <p>{{ t("whatsapp.connected.body") }}</p>
      <Button
        :label="t('whatsapp.connected.disconnect')"
        severity="secondary"
        @click="wa.disconnect"
      />
    </AppCard>

    <!-- Section B: Recipients (CSV input) -->
    <AppCard v-if="wa.state.value === 'open'" class="recipients-card">
      <h2>{{ t("whatsapp.recipients.title") }}</h2>
      <p class="hint">{{ t("whatsapp.recipients.hint") }}</p>
      <pre class="example">{{ t("whatsapp.recipients.example") }}</pre>

      <div class="phone-config">
        <label class="phone-col">
          <span>{{ t("whatsapp.recipients.phoneColumnLabel") }}</span>
          <InputText
            v-model="phoneColumn"
            spellcheck="false"
            autocomplete="off"
            class="phone-col-input"
          />
        </label>
        <label class="phone-col">
          <span>{{ t("whatsapp.recipients.countryCodeLabel") }}</span>
          <InputText
            v-model="countryCode"
            spellcheck="false"
            autocomplete="off"
            inputmode="numeric"
            placeholder="31"
            class="country-code-input"
          />
        </label>
      </div>
      <p class="hint subtle">{{ t("whatsapp.recipients.countryCodeHint") }}</p>

      <div class="csv-input">
        <Textarea
          v-model="csvText"
          rows="8"
          :placeholder="t('whatsapp.recipients.placeholder')"
          class="csv-textarea"
          autoResize
        />
        <label class="file-pick">
          <input type="file" accept=".csv,text/csv,text/plain" @change="onFile" />
          <span>{{ t("whatsapp.recipients.upload") }}</span>
        </label>
      </div>

      <div v-if="parsed.fatal.length" class="fatal">
        <p v-for="code in parsed.fatal" :key="code">
          {{ t(`whatsapp.recipients.errors.${code}`) }}
        </p>
      </div>

      <div v-if="parsed.headers.length" class="parse-summary">
        <p class="counts">
          <strong>{{ validRows.length }}</strong>
          {{ t("whatsapp.recipients.validCount") }}
          <span v-if="parsed.rows.length - validRows.length > 0">
            ,
            <strong>{{ parsed.rows.length - validRows.length }}</strong>
            {{ t("whatsapp.recipients.invalidCount") }}
          </span>
        </p>
        <p v-if="tags.length" class="tags">
          {{ t("whatsapp.recipients.availableTags") }}
          <code v-for="tag in tags" :key="tag" class="tag">{{ "{" + tag + "}" }}</code>
        </p>
      </div>

      <div v-if="parsed.rows.length" class="preview-table-wrap">
        <table class="preview-table">
          <thead>
            <tr>
              <th>#</th>
              <th v-for="h in parsed.headers" :key="h">{{ h }}</th>
              <th>{{ t("whatsapp.recipients.status") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, idx) in parsed.rows"
              :key="idx"
              :class="{ invalid: row.status === 'invalid' }"
            >
              <td>{{ idx + 1 }}</td>
              <td v-for="h in parsed.headers" :key="h">{{ row.fields[h] }}</td>
              <td>
                <span v-if="row.status === 'ok'" class="ok">✓</span>
                <span v-else class="bad">
                  ✗ {{ t(`whatsapp.recipients.errors.${row.error}`) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <!-- Section C: Compose & send -->
    <AppCard
      v-if="wa.state.value === 'open' && validRows.length > 0"
      class="compose-card"
    >
      <h2>{{ t("whatsapp.compose.title") }}</h2>
      <p class="hint">{{ t("whatsapp.compose.hint") }}</p>

      <div class="compose-grid">
        <div class="compose-input">
          <Textarea
            ref="composeRef"
            v-model="template"
            rows="8"
            :placeholder="t('whatsapp.compose.placeholder')"
            class="compose-textarea"
            autoResize
            :disabled="sending"
          />
          <div class="compose-toolbar">
            <EmojiPicker @select="insertEmoji" />
          </div>
          <details class="formatting-help">
            <summary>{{ t("whatsapp.compose.formattingHelp") }}</summary>
            <ul>
              <li><code>*{{ t("whatsapp.compose.bold") }}*</code></li>
              <li><code>_{{ t("whatsapp.compose.italic") }}_</code></li>
              <li><code>~{{ t("whatsapp.compose.strike") }}~</code></li>
              <li><code>`{{ t("whatsapp.compose.mono") }}`</code></li>
            </ul>
          </details>
        </div>

        <div class="compose-preview">
          <h3>{{ t("whatsapp.compose.previewTitle") }}</h3>
          <p v-if="previewSourceRow" class="preview-meta">
            {{ t("whatsapp.compose.previewFor") }}
            <strong>{{ previewSourceRow.fields[phoneColumn.toLowerCase()] }}</strong>
          </p>
          <div class="preview-bubble">
            <span v-if="!previewMerged" class="preview-empty">
              {{ t("whatsapp.compose.previewEmpty") }}
            </span>
            <span v-else v-html="previewHtml" />
          </div>
        </div>
      </div>

      <div v-if="sending || finished" class="send-progress">
        <ProgressBar :value="progress" />
        <p class="progress-line">
          {{ sentCount }} {{ t("whatsapp.compose.sent") }},
          {{ failedCount }} {{ t("whatsapp.compose.failed") }}
          <span v-if="!finished">
            ({{ t("whatsapp.compose.of", { total: validRows.length }) }})
          </span>
        </p>
      </div>

      <div class="send-controls">
        <Button
          v-if="!sending && !finished"
          :label="t('whatsapp.compose.sendButton', { count: validRows.length })"
          :disabled="sendDisabled"
          @click="confirmSend"
        />
        <template v-if="sending">
          <Button
            v-if="!paused"
            :label="t('whatsapp.compose.pause')"
            severity="secondary"
            @click="paused = true"
          />
          <Button
            v-else
            :label="t('whatsapp.compose.resume')"
            @click="paused = false"
          />
          <Button
            :label="t('whatsapp.compose.cancel')"
            severity="danger"
            text
            @click="cancelSend"
          />
        </template>
        <Button
          v-if="finished"
          :label="t('whatsapp.compose.download')"
          severity="secondary"
          @click="downloadResults"
        />
      </div>

      <!-- Per-row send status (shown once at least one row has fired). -->
      <div v-if="Object.keys(sendResults).length" class="send-table-wrap">
        <table class="preview-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{{ t("whatsapp.recipients.status") }}</th>
              <th v-for="h in parsed.headers" :key="h">{{ h }}</th>
              <th>{{ t("whatsapp.compose.sendStatus") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, idx) in validRows"
              :key="row.line"
              :class="{
                'send-current': currentLine === row.line,
                'send-failed': sendResults[row.line]?.status === 'failed',
                'send-sent': sendResults[row.line]?.status === 'sent',
              }"
            >
              <td>{{ idx + 1 }}</td>
              <td><span class="ok">✓</span></td>
              <td v-for="h in parsed.headers" :key="h">{{ row.fields[h] }}</td>
              <td>
                <span v-if="sendResults[row.line]?.status === 'sent'" class="ok">
                  ✓ {{ t("whatsapp.compose.sent") }}
                </span>
                <span v-else-if="sendResults[row.line]?.status === 'failed'" class="bad">
                  ✗ {{ sendResults[row.line]?.error || t("whatsapp.compose.failed") }}
                </span>
                <span v-else-if="sendResults[row.line]?.status === 'sending'" class="sending-cell">
                  …
                </span>
                <span v-else class="muted">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>

<style scoped>
/* Override the canonical 720px container width: the compose
 * pane is genuinely two-column (textarea + WhatsApp preview)
 * and the recipients table benefits from horizontal headroom.
 * Stays centred and on-brand otherwise. */
.wa-container {
  max-width: 64rem;
}

/* ---- Section A: Connect ------------------------------------- */

.instructions {
  margin: 0 0 1rem 1.25rem;
  padding: 0;
  line-height: 1.6;
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
  font-size: 0.95rem;
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

/* ---- Section B: Recipients ---------------------------------- */

.hint {
  color: var(--brand-text-muted);
  font-size: 0.875rem;
  margin: 0;
}
.example {
  background: var(--brand-bg);
  border: 1px solid var(--brand-border);
  border-radius: 0.25rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  margin: 0;
  white-space: pre-wrap;
}
.phone-config {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}
.phone-col {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}
.phone-col-input {
  max-width: 12rem;
}
.country-code-input {
  max-width: 6rem;
}
.subtle {
  font-size: 0.85rem;
  color: var(--brand-text-muted);
  margin: 0;
}
.csv-input {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.csv-textarea {
  width: 100%;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.9rem;
}
.file-pick {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  color: var(--brand-text-muted);
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
  font-size: 0.9rem;
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
  font-size: 0.9rem;
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
  background: #fdecea;
}
.preview-table .ok {
  color: #1b873f;
}
.preview-table .bad {
  color: var(--brand-red);
}

/* ---- Section C: Compose & send ------------------------------ */

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
.compose-textarea {
  width: 100%;
  font-size: 0.95rem;
}
.compose-toolbar {
  display: flex;
  gap: 0.25rem;
  margin: -0.25rem 0 0.25rem;
}
.formatting-help {
  font-size: 0.85rem;
  color: var(--brand-text-muted);
}
.formatting-help ul {
  margin: 0.5rem 0 0 1rem;
  padding: 0;
}
.formatting-help li {
  margin-bottom: 0.2rem;
}
.preview-meta {
  font-size: 0.85rem;
  color: var(--brand-text-muted);
  margin: 0 0 0.5rem;
}
/* WhatsApp's own bubble colour is intentionally preserved — the
 * point of this preview is to show the user what the recipient
 * sees. The lime green is part of the fidelity, not a brand
 * choice. */
.preview-bubble {
  background: #d9fdd3;
  color: #111;
  padding: 0.75rem 1rem;
  border-radius: 0.75rem 0.75rem 0.75rem 0.25rem;
  min-height: 4rem;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 0.95rem;
  line-height: 1.4;
}
.preview-empty {
  color: var(--brand-text-muted);
  font-style: italic;
}
.progress-line {
  margin: 0.5rem 0 0;
  font-size: 0.9rem;
  color: var(--brand-text-muted);
}
.send-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.send-current {
  background: var(--brand-bg);
}
.send-sent .ok {
  color: #1b873f;
}
.send-failed .bad {
  color: var(--brand-red);
}
.sending-cell,
.muted {
  color: var(--brand-text-muted);
}
</style>
