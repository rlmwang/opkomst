/**
 * State for the WhatsApp blast tool.
 *
 * Not Vue Query. the data is ephemeral, single-page, and a
 * server cache would actively work against the "forget when the
 * user leaves" contract. Plain refs + a polling timer.
 *
 * One ping covers two jobs: the page POSTs ``/heartbeat`` every
 * 15s, which both bumps the server-side last-seen timestamp
 * (driving the watchdog tear-down) and returns the current
 * connection state. No need for a separate ``/status`` poll.
 *
 * The QR is fetched on demand whenever the state is anything
 * other than ``open``. Evolution rotates the QR every ~20s, so
 * the page refreshes it on the same cadence.
 */
import { onBeforeUnmount, ref } from "vue";
import { get, post } from "@/api/client";

export type WaState =
  | "open"
  | "connecting"
  | "close"
  | "unknown"
  | "not_configured";

interface StatusBody {
  state: WaState;
}

interface QrBody {
  qr: string | null;
  pairingCode: string | null;
}

const HEARTBEAT_INTERVAL_MS = 15_000;
const QR_REFRESH_INTERVAL_MS = 20_000;

export function useWhatsApp() {
  const state = ref<WaState>("unknown");
  const qr = ref<string | null>(null);
  const pairingCode = ref<string | null>(null);
  const lastError = ref<string | null>(null);

  let heartbeatTimer: number | null = null;
  let qrTimer: number | null = null;

  async function fetchStatus(): Promise<void> {
    try {
      const body = await post<StatusBody>("/api/v1/whatsapp/heartbeat", {});
      state.value = body.state;
      lastError.value = null;
    } catch (e) {
      state.value = "unknown";
      lastError.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function fetchQr(): Promise<void> {
    try {
      const body = await get<QrBody>("/api/v1/whatsapp/qr");
      qr.value = body.qr;
      pairingCode.value = body.pairingCode;
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e);
    }
  }

  function startPolling(): void {
    if (heartbeatTimer !== null) return;
    void fetchStatus();
    void fetchQr();
    heartbeatTimer = window.setInterval(() => void fetchStatus(), HEARTBEAT_INTERVAL_MS);
    // The QR auto-refresh only matters while we're not yet linked.
    qrTimer = window.setInterval(() => {
      if (state.value !== "open" && state.value !== "not_configured") {
        void fetchQr();
      }
    }, QR_REFRESH_INTERVAL_MS);
  }

  function stopPolling(): void {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    if (qrTimer !== null) {
      window.clearInterval(qrTimer);
      qrTimer = null;
    }
  }

  async function disconnect(): Promise<void> {
    stopPolling();
    try {
      await post("/api/v1/whatsapp/logout", {});
    } catch {
      // Best-effort. The watchdog is the safety net.
    }
    state.value = "close";
    qr.value = null;
    pairingCode.value = null;
  }

  async function send(number: string, text: string): Promise<{ ok: boolean; error?: string }> {
    try {
      await post("/api/v1/whatsapp/send", { number, text });
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  onBeforeUnmount(() => {
    stopPolling();
    // Best-effort ``pagehide`` already runs in the page itself for
    // the tab-close case; calling logout here covers normal SPA
    // navigation away from the page.
    void disconnect();
  });

  return {
    state,
    qr,
    pairingCode,
    lastError,
    startPolling,
    stopPolling,
    fetchQr,
    disconnect,
    send,
  };
}
