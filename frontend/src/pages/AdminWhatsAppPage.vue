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
import Dialog from "primevue/dialog";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import ProgressBar from "primevue/progressbar";
import Select from "primevue/select";
import Textarea from "primevue/textarea";
import { computed, ref } from "vue";
import { onBeforeUnmount, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import EmojiPicker from "@/components/EmojiPicker.vue";
import { useWhatsApp } from "@/composables/useWhatsApp";
import { COUNTRIES, type Country, flagEmoji } from "@/lib/countries";
import { applyMerge, mergeTags, parseCsv } from "@/lib/csv";
import { whatsappFormat } from "@/lib/whatsappFormat";

const { t } = useI18n();
const wa = useWhatsApp();

// Section B state. Kept in the page (not the composable) since
// it's purely client-side and doesn't outlive the page mount.
const csvText = ref("");
const phoneColumn = ref("nummer");
// Default country code applied to bare national numbers in the
// CSV (e.g. ``0612345678`` becomes ``31612345678``). Defaults to
// NL since that's the overwhelmingly common case for this app;
// the dropdown lets the user pick a different one.
const country = ref<Country>(COUNTRIES.find((c) => c.iso === "NL") ?? COUNTRIES[0]);
const countryCode = computed(() => country.value.dialCode);
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

// Pacing between sends. Default is 6s (mid-point of WhatsApp's
// own anti-spam tolerance for a freshly-linked device); 2s is
// the floor — below that the server starts dropping
// "you're sending too fast" warnings and risks the linked
// session being unlinked. Cap at 60s to catch typos.
const DELAY_MIN = 2;
const DELAY_MAX = 60;
const delaySeconds = ref(6);

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

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** ±20 % around the user-configured base delay. The randomness
 * blunts the bot-pattern fingerprint that a perfectly-periodic
 * cadence would otherwise create. */
function nextDelayMs(): number {
  const base = delaySeconds.value * 1000;
  return base * (0.8 + Math.random() * 0.4);
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
      await sleep(nextDelayMs());
    }
  }

  currentLine.value = null;
  sending.value = false;
}

const confirmOpen = ref(false);

function openConfirm(): void {
  confirmOpen.value = true;
}

function acceptConfirm(): void {
  confirmOpen.value = false;
  void runSendLoop();
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

// Browsers ignore custom strings here, but setting ``returnValue``
// or calling ``preventDefault`` triggers their generic
// "Leave site? Changes you made may not be saved." prompt. Just
// enough to stop the user from accidentally tab-closing
// mid-blast. Skip the prompt when the loop isn't running.
function onBeforeUnload(e: BeforeUnloadEvent): void {
  if (!sending.value) return;
  e.preventDefault();
  e.returnValue = "";
}

onMounted(() => {
  wa.startPolling();
  window.addEventListener("pagehide", onPageHide);
  window.addEventListener("beforeunload", onBeforeUnload);
});

onBeforeUnmount(() => {
  window.removeEventListener("pagehide", onPageHide);
  window.removeEventListener("beforeunload", onBeforeUnload);
});
</script>

<template>
  <AppHeader />
  <div class="container wa-container stack">
    <h1>{{ t("whatsapp.title") }}</h1>
    <p class="muted">{{ t("whatsapp.lede") }}</p>

    <AppCard class="wa-card">
      <!-- Connect: big QR while not linked, slim "linked" row otherwise. -->
      <div
        v-if="wa.state.value !== 'open' && wa.state.value !== 'not_configured'"
        class="connect"
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
      </div>

      <div v-if="wa.state.value === 'open'" class="linked">
        <span class="linked-pill">✓ {{ t("whatsapp.connected.linked") }}</span>
        <Button
          :label="t('whatsapp.connected.disconnect')"
          severity="secondary"
          text
          class="disconnect-btn"
          @click="wa.disconnect"
        />
      </div>

      <!-- Recipients + composer flow once linked. No "Step 2 / Step 3"
           framing; the page is short enough to just read top-to-bottom. -->
      <template v-if="wa.state.value === 'open'">
        <h2 class="section-h">{{ t("whatsapp.recipients.title") }}</h2>
        <p class="muted">{{ t("whatsapp.recipients.hint") }}</p>

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
            <Select
              v-model="country"
              :options="COUNTRIES"
              optionLabel="name"
              filter
              filterPlaceholder="..."
              class="country-select"
            >
              <template #value="{ value }">
                <span v-if="value" class="country-row">
                  <span class="flag">{{ flagEmoji(value.iso) }}</span>
                  <span>+{{ value.dialCode }}</span>
                </span>
              </template>
              <template #option="{ option }">
                <span class="country-row">
                  <span class="flag">{{ flagEmoji(option.iso) }}</span>
                  <span class="country-name">{{ option.name }}</span>
                  <span class="country-dial">+{{ option.dialCode }}</span>
                </span>
              </template>
            </Select>
          </label>
        </div>

        <Textarea
          v-model="csvText"
          rows="8"
          class="csv-textarea"
        />

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
                <td v-for="h in parsed.headers" :key="h">
                  {{
                    h === phoneColumn.toLowerCase()
                      ? row.phone || row.fields[h]
                      : row.fields[h]
                  }}
                </td>
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

        <h2 class="section-h">{{ t("whatsapp.compose.title") }}</h2>
        <p class="muted">{{ t("whatsapp.compose.hint") }}</p>

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
                <span class="fmt"><code>*</code><strong>{{ t("whatsapp.compose.bold") }}</strong><code>*</code></span>
                <span class="fmt"><code>_</code><em>{{ t("whatsapp.compose.italic") }}</em><code>_</code></span>
                <span class="fmt"><code>~</code><s>{{ t("whatsapp.compose.strike") }}</s><code>~</code></span>
                <span class="fmt"><code>`{{ t("whatsapp.compose.mono") }}`</code></span>
              </div>
            </div>

            <div class="compose-preview">
              <div class="preview-bubble">
                <span v-if="!previewMerged" class="preview-empty">
                  {{ t("whatsapp.compose.previewEmpty") }}
                </span>
                <span v-else v-html="previewHtml" />
              </div>
            </div>
          </div>

          <div v-if="!sending && !finished" class="delay-row">
            <label class="delay-label">
              <span>{{ t("whatsapp.compose.delayLabel") }}</span>
              <InputNumber
                v-model="delaySeconds"
                :min="DELAY_MIN"
                :max="DELAY_MAX"
                :step="1"
                showButtons
                buttonLayout="horizontal"
                suffix=" s"
                :inputStyle="{ width: '4rem', textAlign: 'right' }"
              />
            </label>
            <p class="muted delay-hint">{{ t("whatsapp.compose.delayHint") }}</p>
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

          <p v-if="sending" class="closing-warning">
            ⚠️ {{ t("whatsapp.compose.dontCloseWarning") }}
          </p>

          <div class="send-controls">
            <Button
              v-if="!sending && !finished"
              :label="t('whatsapp.compose.sendButton', { count: validRows.length })"
              :disabled="sendDisabled"
              @click="openConfirm"
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
          </div>

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
                  <td v-for="h in parsed.headers" :key="h">
                    {{
                      h === phoneColumn.toLowerCase()
                        ? row.phone || row.fields[h]
                        : row.fields[h]
                    }}
                  </td>
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

          <div v-if="finished" class="download-row">
            <Button
              :label="t('whatsapp.compose.download')"
              severity="secondary"
              @click="downloadResults"
            />
          </div>
      </template>
    </AppCard>

    <Dialog
      v-model:visible="confirmOpen"
      modal
      :header="t('whatsapp.compose.confirmHeader')"
      :style="{ width: '420px' }"
      :closable="true"
    >
      <p class="confirm-lead">
        {{ t("whatsapp.compose.confirmLead", { count: validRows.length }) }}
      </p>
      <div class="preview-bubble confirm-bubble">
        <span v-if="!previewMerged" class="preview-empty">
          {{ t("whatsapp.compose.previewEmpty") }}
        </span>
        <span v-else v-html="previewHtml" />
      </div>
      <template #footer>
        <Button
          :label="t('common.cancel')"
          severity="secondary"
          text
          @click="confirmOpen = false"
        />
        <Button
          :label="t('whatsapp.compose.confirmAccept', { count: validRows.length })"
          @click="acceptConfirm"
        />
      </template>
    </Dialog>
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

/* The whole flow lives in one card now (connect at top, then
 * recipients, then compose). Breathing room comes from
 * ``.section-h`` margins, not from card boundaries. */
.wa-card :deep(.card) > * + * {
  margin-top: 1rem;
}
.section-h {
  margin-top: 2rem;
}

/* ---- Connect block ----------------------------------------- */

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
.disconnect-btn {
  margin-left: auto;
}
.linked-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  background: #e3f7e8;
  color: #1b873f;
  border: 1px solid #cfe8d4;
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

/* ---- Recipients block -------------------------------------- */

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
.country-select {
  min-width: 8rem;
}
.country-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}
.country-row .flag {
  font-size: 1.1rem;
  line-height: 1;
}
.country-row .country-name {
  flex: 1;
}
.country-row .country-dial {
  color: var(--brand-text-muted);
  font-variant-numeric: tabular-nums;
}
.csv-textarea {
  width: 100%;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.9rem;
}
/* Lock the height so a big paste scrolls inside the box rather
 * than pushing the rest of the page down. ``resize: none`` keeps
 * the box at the ``rows="8"`` initial height; the user can scroll
 * inside it but not drag the corner. */
.csv-textarea :deep(textarea) {
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

/* ---- Compose block ----------------------------------------- */

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
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin: -0.25rem 0 0.25rem;
  font-size: 0.85rem;
  color: var(--brand-text-muted);
}
.fmt code {
  background: var(--brand-bg);
  padding: 0 0.15rem;
  border-radius: 0.2rem;
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
.confirm-lead {
  margin: 0 0 0.75rem;
}
.confirm-bubble {
  max-height: 18rem;
  overflow-y: auto;
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
  font-size: 0.9rem;
}
.delay-hint {
  font-size: 0.85rem;
  margin: 0;
  flex-basis: 100%;
}
.closing-warning {
  background: #fff7e6;
  border: 1px solid #f5d8a0;
  color: #7a4a00;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  margin: 0;
  font-size: 0.9rem;
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
